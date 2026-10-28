import numpy as np
import pandas as pd
import pytest

from kc_house.evaluate import error_by_price_band, regression_metrics


def test_perfect_predictions_have_zero_error():
    truth = pd.Series([100_000.0, 200_000.0, 300_000.0])

    metrics = regression_metrics(truth, truth.to_numpy())

    assert metrics["r2"] == pytest.approx(1.0)
    assert metrics["mae"] == 0
    assert metrics["median_abs_pct_error"] == 0


def test_metrics_report_known_errors_in_dollars_and_percent():
    truth = pd.Series([100.0, 200.0])
    predicted = np.array([110.0, 180.0])

    metrics = regression_metrics(truth, predicted)

    assert metrics["mae"] == pytest.approx(15.0)
    assert metrics["mean_error"] == pytest.approx(-5.0)
    assert metrics["median_abs_pct_error"] == pytest.approx(10.0)


def test_price_bands_cover_every_house_exactly_once():
    truth = pd.Series(np.arange(1, 101, dtype=float))

    bands = error_by_price_band(truth, truth.to_numpy() + 1, n_bands=4)

    assert [band["band"] for band in bands] == [1, 2, 3, 4]
    assert sum(band["houses"] for band in bands) == 100
    assert all(band["mean_error"] == pytest.approx(1.0) for band in bands)
