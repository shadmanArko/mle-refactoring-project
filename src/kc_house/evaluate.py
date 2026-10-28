"""Regression metrics and error analysis."""

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error


def regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """Headline errors, in dollars and in percent of the true price."""
    truth = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    errors = predicted - truth
    return {
        "r2": float(r2_score(truth, predicted)),
        "rmse": float(root_mean_squared_error(truth, predicted)),
        "mae": float(mean_absolute_error(truth, predicted)),
        "median_abs_pct_error": float(np.median(np.abs(errors) / truth) * 100),
        "mean_error": float(errors.mean()),
    }


def error_by_price_band(
    y_true: pd.Series, y_pred: np.ndarray, n_bands: int = 4
) -> list[dict[str, float]]:
    """Errors per price band; one overall number hides who is served badly."""
    frame = pd.DataFrame(
        {"price": np.asarray(y_true, dtype=float), "predicted": np.asarray(y_pred)}
    )
    frame["band"] = pd.qcut(frame["price"], n_bands, labels=False)
    rows: list[dict[str, float]] = []
    for band, group in frame.groupby("band"):
        errors = group["predicted"] - group["price"]
        rows.append(
            {
                "band": int(band) + 1,  # type: ignore[arg-type]
                "price_min": float(group["price"].min()),
                "price_max": float(group["price"].max()),
                "houses": len(group),
                "mae": float(errors.abs().mean()),
                "median_abs_pct_error": float(
                    (errors.abs() / group["price"]).median() * 100
                ),
                "mean_error": float(errors.mean()),
            }
        )
    return rows
