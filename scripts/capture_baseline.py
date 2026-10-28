"""Freeze the notebook's results as golden values for the refactor.

Executes the notebook's data-preparation, feature-engineering and modeling
cells verbatim (plots and exploratory printing are skipped), then writes:

* ``tests/golden/clean_frame.csv.gz``  - the frame after cleaning + features
* ``tests/golden/baseline_metrics.json`` - shapes, columns, scores, best params

The refactored pipeline must reproduce these numbers (see ADR-0002).
Run from the repository root: ``uv run python scripts/capture_baseline.py``.
"""

import contextlib
import hashlib
import io
import json
from pathlib import Path

NOTEBOOK = Path("King-County.ipynb")
GOLDEN_DIR = Path("tests/golden")

# Cell indices of the notebook that change data or fit models, in order.
PREP_AND_FEATURES = [6, 7, 28, 30, 35, 38, 41, 42, 43, 56, 60, 67, 68, 69, 70]
SPLIT = [78, 79, 80, 81, 82]
GRADE_ONLY = [86, 88, 89]
GRADE_AND_CHANGE = [94, 95, 96]
POLYNOMIAL = [100, 101, 102, 103, 104]
ELASTIC_NET = [117, 119]


def adjusted_r2(r2: float, n_rows: int, n_features: int) -> float:
    """Adjusted R^2 with the same formula the notebook uses."""
    return 1 - (1 - r2) * (n_rows - 1) / (n_rows - n_features - 1)


def run_cells(cells: list[int], namespace: dict) -> None:
    notebook = json.loads(NOTEBOOK.read_text())
    for index in cells:
        source = "".join(notebook["cells"][index]["source"])
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source, f"<cell {index}>", "exec"), namespace)


def main() -> None:
    ns: dict = {}
    metrics: dict = {}

    run_cells(PREP_AND_FEATURES, ns)
    frame = ns["kc_data"]
    metrics["clean_shape"] = list(frame.shape)
    metrics["clean_columns"] = list(frame.columns)

    run_cells(SPLIT, ns)
    metrics["feature_columns"] = list(ns["X"].columns)
    metrics["x_train_shape"] = list(ns["X_train"].shape)
    metrics["x_test_shape"] = list(ns["X_test"].shape)
    metrics["train_index_sha256"] = hashlib.sha256(
        ",".join(map(str, ns["X_train"].index)).encode()
    ).hexdigest()

    run_cells(GRADE_ONLY, ns)
    variables = ns["variables"]
    r2 = ns["model_lin_reg"].score(ns["X_test"][variables], ns["y_test"])
    metrics["grade_only_adj_r2"] = adjusted_r2(r2, len(ns["X_test"]), len(variables))

    run_cells(GRADE_AND_CHANGE, ns)
    variables = ns["variables"]
    r2 = ns["model_lin_reg"].score(ns["X_test"][variables], ns["y_test"])
    metrics["grade_and_change_adj_r2"] = adjusted_r2(
        r2, len(ns["X_test"]), len(variables)
    )

    run_cells(POLYNOMIAL, ns)
    x_test_sq = ns["X_test_sq"]
    r2 = ns["model_lin_reg"].score(x_test_sq, ns["y_test"])
    metrics["polynomial_adj_r2"] = adjusted_r2(
        r2, x_test_sq.shape[0], x_test_sq.shape[1]
    )

    run_cells(ELASTIC_NET, ns)
    elastic = ns["elastic"]
    metrics["elastic_best_params"] = ns["elastic_cv"].best_params_
    metrics["elastic_cv_best_r2"] = float(ns["elastic_cv"].best_score_)
    metrics["elastic_test_r2"] = float(elastic.score(ns["X_test_poly"], ns["y_test"]))

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(GOLDEN_DIR / "clean_frame.csv.gz", index=True)
    (GOLDEN_DIR / "baseline_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps({k: v for k, v in metrics.items() if "columns" not in k}, indent=2)
    )


if __name__ == "__main__":
    main()
