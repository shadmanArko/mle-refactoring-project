import numpy as np
import pandas as pd
import pytest

from kc_house.config import CENTER_LAT, CENTER_LONG, KM_PER_DEGREE
from kc_house.features import WaterDistance, add_center_distance


def houses(lat, long, waterfront):
    return pd.DataFrame({"lat": lat, "long": long, "waterfront": waterfront})


def test_center_distance_is_zero_at_the_reference_point_and_scales_with_latitude():
    frame = pd.DataFrame(
        {"lat": [CENTER_LAT, CENTER_LAT + 1], "long": [CENTER_LONG, CENTER_LONG]}
    )

    result = add_center_distance(frame)

    assert result.loc[0, "center_distance"] == pytest.approx(0, abs=1e-9)
    assert result.loc[1, "center_distance"] == pytest.approx(KM_PER_DEGREE)


def test_water_distance_is_distance_to_nearest_waterfront_house():
    train = houses([47.5, 47.7], [-122.2, -122.3], [1, 0])
    new = houses([47.6, 47.5], [-122.2, -122.2], [0, 0])

    result = WaterDistance().fit(train).transform(new)

    assert result["water_distance"].tolist() == pytest.approx(
        [0.1 * KM_PER_DEGREE, 0.0]
    )


def test_water_distance_ignores_extra_waterfront_houses_seen_only_at_transform_time():
    """Leakage guard: reference points come from fit(), never from transform()."""
    train = houses([47.5], [-122.2], [1])
    test = houses([47.9, 47.6], [-122.2, -122.2], [1, 0])
    transformer = WaterDistance().fit(train)

    result = transformer.transform(test)

    # The first test house is waterfront, but it was not in training, so its
    # distance is to the training waterfront house, not zero.
    assert result.loc[0, "water_distance"] == pytest.approx(0.4 * KM_PER_DEGREE)
    assert len(transformer.reference_lat_) == 1


def test_water_distance_is_unchanged_by_test_rows_labels():
    train = houses([47.5, 47.7], [-122.2, -122.3], [1, 0])
    test = houses([47.6], [-122.25], [0])
    flipped = test.assign(waterfront=1)
    transformer = WaterDistance().fit(train)

    np.testing.assert_array_equal(
        transformer.transform(test)["water_distance"].to_numpy(),
        transformer.transform(flipped)["water_distance"].to_numpy(),
    )


def test_water_distance_does_not_depend_on_chunk_size():
    rng = np.random.default_rng(0)
    frame = houses(
        rng.uniform(47.3, 47.8, 50), rng.uniform(-122.5, -121.8, 50), [1] * 5 + [0] * 45
    )

    small = WaterDistance(chunk_size=1).fit(frame).transform(frame)
    large = WaterDistance(chunk_size=1000).fit(frame).transform(frame)

    pd.testing.assert_frame_equal(small, large)


def test_water_distance_refuses_to_fit_without_waterfront_houses():
    with pytest.raises(ValueError, match="no waterfront"):
        WaterDistance().fit(houses([47.5], [-122.2], [0]))
