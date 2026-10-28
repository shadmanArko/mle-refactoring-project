"""Training CLI: compare models, tune the production model, evaluate, save.

Run ``uv run python -m kc_house.train`` (or ``kc-train``). Outputs go to
``artifacts/``: the skops model, ``metrics.json`` and ``model_card.md``.
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

import pandas as pd
import skops.io as sio
from sklearn.base import clone
from sklearn.model_selection import GridSearchCV, cross_val_score
from sklearn.pipeline import Pipeline

from kc_house.config import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_PATH,
    MIN_ACCEPTABLE_R2,
    RANDOM_STATE,
    TEST_SIZE,
)
from kc_house.data import (
    Split,
    load_raw,
    make_grouped_split,
    make_temporal_split,
    make_training_split,
)
from kc_house.evaluate import error_by_price_band, regression_metrics
from kc_house.models import build_baselines, build_candidates, build_production_model
from kc_house.report import render_model_card

logger = logging.getLogger(__name__)

# The notebook's grid: both penalties stay active, 9 combinations x 5 folds.
PARAM_GRID = {
    "model__regressor__alpha": [0.01, 0.1, 1],
    "model__regressor__l1_ratio": [0.2, 0.5, 0.8],
}


class BelowFloorError(RuntimeError):
    """The tuned model did not reach the minimum acceptable held-out R^2."""


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


def tune_production_model(
    X_train: pd.DataFrame, y_train: pd.Series, cv: int = 5
) -> GridSearchCV:
    """Grid search the notebook's ElasticNet pipeline on training data only."""
    search = GridSearchCV(
        build_production_model(),
        PARAM_GRID,
        cv=cv,
        scoring="r2",
        n_jobs=1,
        error_score="raise",  # pyright: ignore[reportArgumentType]
    )
    return search.fit(X_train, y_train)


def run_training(
    data_path: Path = DEFAULT_DATA_PATH,
    out_dir: Path = DEFAULT_ARTIFACTS_DIR,
    *,
    cv: int = 5,
    compare_models: bool = True,
    card_path: Path | None = None,
) -> dict:
    """Train, evaluate and save the production model; return the full report."""
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

    # 2. Other model families, judged on cross-validation only.
    if compare_models:
        for name, candidate in build_candidates().items():
            logger.info("Cross-validating candidate %s", name)
            comparison.append(
                {"name": name, "role": "candidate", **_cv_r2(candidate, split, cv)}
            )

    # 3. Tune the production model on training data only.
    logger.info("Tuning the production model (%d-fold grid search)", cv)
    search = tune_production_model(X_train, y_train, cv)
    best = cast(Pipeline, search.best_estimator_)
    best_row = int(search.best_index_)
    comparison.append(
        {
            "name": "elastic_net_poly",
            "role": "production",
            "cv_r2_mean": float(search.best_score_),
            "cv_r2_std": float(search.cv_results_["std_test_score"][best_row]),
        }
    )

    # 4. The test set is touched exactly once, for the tuned model.
    test_predictions = best.predict(X_test)
    test_metrics = regression_metrics(y_test, test_predictions)
    comparison[-1]["test_r2"] = test_metrics["r2"]
    logger.info("Held-out R^2 %.4f (floor %.2f)", test_metrics["r2"], MIN_ACCEPTABLE_R2)
    if test_metrics["r2"] < MIN_ACCEPTABLE_R2:
        raise BelowFloorError(
            f"Held-out R^2 {test_metrics['r2']:.3f} is below {MIN_ACCEPTABLE_R2}"
        )

    # 5. Robustness: same tuned settings under stricter ways of splitting.
    robustness = {
        "random (notebook)": test_metrics,
        "grouped by house id": _fit_and_score(best, make_grouped_split(raw)),
        "temporal (train past, test future)": _fit_and_score(
            best, make_temporal_split(raw)
        ),
    }

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
            "python": platform.python_version(),
            "scikit_learn": version("scikit-learn"),
            "pandas": version("pandas"),
            "sale_dates": [
                str(pd.to_datetime(raw["date"], format="%m/%d/%Y").min().date()),
                str(pd.to_datetime(raw["date"], format="%m/%d/%Y").max().date()),
            ],
        },
        "best_params": search.best_params_,
        "param_grid": PARAM_GRID,
        "min_acceptable_r2": MIN_ACCEPTABLE_R2,
        "comparison": comparison,
        "test_metrics": test_metrics,
        "split_robustness": robustness,
        "error_by_price_band": error_by_price_band(y_test, test_predictions),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.skops"
    sio.dump(best, model_path)
    # Recorded so the serving code can load with an explicit allow-list.
    report["skops_trusted_types"] = sorted(sio.get_untrusted_types(file=model_path))
    (out_dir / "metrics.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    card = card_path or out_dir / "model_card.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(render_model_card(report))
    logger.info("Saved model to %s and model card to %s", model_path, card)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--cv", type=int, default=5, help="cross-validation folds")
    parser.add_argument(
        "--skip-comparison",
        action="store_true",
        help="skip the random forest / boosting / ridge comparison (faster)",
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
            card_path=args.card,
        )
    except BelowFloorError as error:
        logger.error("%s", error)
        return 1
    print(json.dumps(report["test_metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
