import numpy as np
import pandas as pd
import pytest

from kc_house.evaluate import (
    error_by_price_band,
    interval_coverage,
    ratio_interval,
    regression_metrics,
)


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


def test_ratio_interval_holds_the_requested_share_of_prices():
    rng = np.random.default_rng(0)
    predicted = rng.uniform(200_000, 900_000, 5000)
    truth = pd.Series(predicted * rng.normal(1.0, 0.1, 5000))

    interval = ratio_interval(truth, predicted, coverage=0.8)

    assert interval["low_ratio"] < 1.0 < interval["high_ratio"]
    assert interval_coverage(truth, predicted, interval) == pytest.approx(0.8, abs=0.01)


def test_interval_widens_in_dollars_as_the_price_grows():
    interval = {"coverage": 0.8, "low_ratio": 0.9, "high_ratio": 1.1}

    cheap = 200_000 * interval["high_ratio"] - 200_000 * interval["low_ratio"]
    pricey = 900_000 * interval["high_ratio"] - 900_000 * interval["low_ratio"]

    assert pricey > cheap
