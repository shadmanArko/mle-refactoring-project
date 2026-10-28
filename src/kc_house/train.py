"""Training CLI: compare models, tune the champion, evaluate, save.

Run ``uv run kc-train``. Outputs go to ``artifacts/``: the full model, the
six-question estimator served by the API, ``metrics.json`` and ``model_card.md``.
"""

import argparse
import hashlib
import json
import logging
import platform
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import skops.io as sio
from sklearn.base import clone
from sklearn.model_selection import (
    GridSearchCV,
    RandomizedSearchCV,
    cross_val_predict,
    cross_val_score,
)
from sklearn.pipeline import Pipeline

from kc_house.config import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_PATH,
    ESTIMATE_INPUTS,
    MIN_ACCEPTABLE_R2,
    MIN_ACCEPTABLE_R2_ESTIMATE,
    RANDOM_STATE,
    SEARCH_ITERATIONS,
    TEST_SIZE,
)
from kc_house.data import (
    Split,
    load_raw,
    make_grouped_split,
    make_temporal_split,
    make_training_split,
)
from kc_house.estimator import build_estimator
from kc_house.evaluate import (
    error_by_price_band,
    interval_coverage,
    ratio_interval,
    regression_metrics,
)
from kc_house.models import (
    PRODUCTION_SEARCH_SPACE,
    build_baselines,
    build_candidates,
    build_production_model,
    build_reference_model,
)
from kc_house.report import render_model_card

logger = logging.getLogger(__name__)

# The notebook's grid: both penalties stay active, 9 combinations x 5 folds.
REFERENCE_PARAM_GRID = {
    "model__regressor__alpha": [0.01, 0.1, 1],
    "model__regressor__l1_ratio": [0.2, 0.5, 0.8],
}


class BelowFloorError(RuntimeError):
    """A tuned model did not reach its minimum acceptable held-out R^2."""


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_sha256(index: pd.Index) -> str:
    return hashlib.sha256(",".join(map(str, index)).encode()).hexdigest()


def _cv_r2(pipeline: Pipeline, split: Split, cv: int) -> dict[str, float]:
    X_train, _, y_train, _ = split
    scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="r2")
    return {"cv_r2_mean": float(scores.mean()), "cv_r2_std": float(scores.std())}


def _fit_and_score(pipeline: Pipeline, split: Split) -> dict[str, float]:
    X_train, X_test, y_train, y_test = split
    fitted = cast(Pipeline, clone(pipeline)).fit(X_train, y_train)
    return regression_metrics(y_test, fitted.predict(X_test))


def _search_row(name: str, role: str, search) -> dict:
    best = int(search.best_index_)
    return {
        "name": name,
        "role": role,
        "cv_r2_mean": float(search.best_score_),
        "cv_r2_std": float(search.cv_results_["std_test_score"][best]),
    }


def tune_reference_model(
    X_train: pd.DataFrame, y_train: pd.Series, cv: int = 5
) -> GridSearchCV:
    """Grid search the notebook's ElasticNet pipeline on training data only."""
    search = GridSearchCV(
        build_reference_model(),
        REFERENCE_PARAM_GRID,
        cv=cv,
        scoring="r2",
        n_jobs=1,
        error_score="raise",  # pyright: ignore[reportArgumentType]
    )
    return search.fit(X_train, y_train)


def tune_production_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: int = 5,
    iterations: int = SEARCH_ITERATIONS,
) -> RandomizedSearchCV:
    """Random search over gradient-boosting settings on training data only."""
    search = RandomizedSearchCV(
        build_production_model(),
        PRODUCTION_SEARCH_SPACE,
        n_iter=iterations,
        cv=cv,
        scoring="r2",
        random_state=RANDOM_STATE,
        n_jobs=1,
        error_score="raise",  # pyright: ignore[reportArgumentType]
    )
    return search.fit(X_train, y_train)


def _require_floor(name: str, r2: float, floor: float) -> None:
    logger.info("%s held-out R^2 %.4f (floor %.2f)", name, r2, floor)
    if r2 < floor:
        raise BelowFloorError(f"{name} held-out R^2 {r2:.3f} is below {floor}")


def _save(model: Pipeline, path: Path) -> list[str]:
    sio.dump(model, path)
    # Recorded so the serving code can load with an explicit allow-list.
    return sorted(sio.get_untrusted_types(file=path))


def run_training(
    data_path: Path = DEFAULT_DATA_PATH,
    out_dir: Path = DEFAULT_ARTIFACTS_DIR,
    *,
    cv: int = 5,
    compare_models: bool = True,
    search_iterations: int = SEARCH_ITERATIONS,
    card_path: Path | None = None,
) -> dict:
    """Train, evaluate and save both models; return the full report."""
    raw = load_raw(data_path)
    split = make_training_split(raw)
    X_train, X_test, y_train, y_test = split

    # 1. Baselines first: they define what complexity has to earn.
    comparison: list[dict] = []
    for name, baseline in build_baselines().items():
        logger.info("Scoring baseline %s", name)
        comparison.append(
            {"name": name, "role": "baseline", **_cv_r2(baseline, split, cv)}
            | {"test_r2": _fit_and_score(baseline, split)["r2"]}
        )

    # 2. The notebook's model, kept as the documented reference.
    logger.info("Tuning the reference model (notebook ElasticNet)")
    reference = tune_reference_model(X_train, y_train, cv)
    reference_row = _search_row("elastic_net_poly", "reference", reference)
    # Reporting only: the reference's test score is never used to choose anything.
    reference_row["test_r2"] = regression_metrics(y_test, reference.predict(X_test))[
        "r2"
    ]
    comparison.append(reference_row)

    # 3. Other families, judged on cross-validation only.
    if compare_models:
        for name, candidate in build_candidates().items():
            logger.info("Cross-validating candidate %s", name)
            comparison.append(
                {"name": name, "role": "candidate", **_cv_r2(candidate, split, cv)}
            )

    # 4. Tune the champion on training data only.
    logger.info("Tuning the champion (%d random settings)", search_iterations)
    search = tune_production_model(X_train, y_train, cv, search_iterations)
    best = cast(Pipeline, search.best_estimator_)
    production_row = _search_row("hist_gradient_boosting", "production", search)
    comparison.append(production_row)

    # 5. The test set is used once to judge the champion.
    test_predictions = best.predict(X_test)
    test_metrics = regression_metrics(y_test, test_predictions)
    production_row["test_r2"] = test_metrics["r2"]
    _require_floor("Champion", test_metrics["r2"], MIN_ACCEPTABLE_R2)

    # 6. Robustness: same settings under stricter ways of splitting.
    robustness = {
        "random (notebook)": test_metrics,
        "grouped by house id": _fit_and_score(best, make_grouped_split(raw)),
        "temporal (train past, test future)": _fit_and_score(
            best, make_temporal_split(raw)
        ),
    }

    # 7. The six-question estimator that the website uses.
    logger.info("Training the six-question estimator")
    estimator = build_estimator(best).fit(X_train, y_train)
    estimate_predictions = estimator.predict(X_test)
    estimate_metrics = regression_metrics(y_test, estimate_predictions)
    _require_floor("Estimator", estimate_metrics["r2"], MIN_ACCEPTABLE_R2_ESTIMATE)

    # The price range shown to visitors is calibrated on out-of-fold predictions of
    # the training data, then checked on the untouched test set.
    logger.info("Calibrating the 80 percent price range")
    out_of_fold = np.asarray(
        cross_val_predict(
            build_estimator(best, unknown="global"), X_train, y_train, cv=cv
        )
    )
    interval = ratio_interval(y_train, out_of_fold)
    interval["test_coverage"] = interval_coverage(
        y_test, estimate_predictions, interval
    )

    dates = pd.to_datetime(raw["date"], format="%m/%d/%Y")
    report = {
        "metadata": {
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "git_sha": _git_sha(),
            "data_sha256": _file_sha256(data_path),
            "data_rows": len(raw),
            "train_rows": len(X_train),
            "test_rows": len(X_test),
            "train_index_sha256": _index_sha256(X_train.index),
            "random_state": RANDOM_STATE,
            "test_size": TEST_SIZE,
            "cv_folds": cv,
            "search_iterations": search_iterations,
            "python": platform.python_version(),
            "scikit_learn": version("scikit-learn"),
            "pandas": version("pandas"),
            "sale_dates": [str(dates.min().date()), str(dates.max().date())],
        },
        "best_params": search.best_params_,
        "reference_params": reference.best_params_,
        "min_acceptable_r2": MIN_ACCEPTABLE_R2,
        "comparison": comparison,
        "test_metrics": test_metrics,
        "split_robustness": robustness,
        "error_by_price_band": error_by_price_band(y_test, test_predictions),
        "estimator": {
            "inputs": ESTIMATE_INPUTS,
            "min_acceptable_r2": MIN_ACCEPTABLE_R2_ESTIMATE,
            "test_metrics": estimate_metrics,
            "interval": interval,
            "error_by_price_band": error_by_price_band(y_test, estimate_predictions),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    report["skops_trusted_types"] = {
        "model": _save(best, out_dir / "model.skops"),
        "estimator": _save(estimator, out_dir / "estimator.skops"),
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    card = card_path or out_dir / "model_card.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(render_model_card(report))
    logger.info("Saved models to %s and model card to %s", out_dir, card)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--cv", type=int, default=5, help="cross-validation folds")
    parser.add_argument(
        "--search-iterations",
        type=int,
        default=SEARCH_ITERATIONS,
        help="random gradient-boosting settings to try",
    )
    parser.add_argument(
        "--skip-comparison",
        action="store_true",
        help="skip the ridge / random forest comparison (faster)",
    )
    parser.add_argument("--card", type=Path, help="where to write the model card")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = run_training(
            args.data,
            args.out,
            cv=args.cv,
            compare_models=not args.skip_comparison,
            search_iterations=args.search_iterations,
            card_path=args.card,
        )
    except BelowFloorError as error:
        logger.error("%s", error)
        return 1
    print(json.dumps(report["test_metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
