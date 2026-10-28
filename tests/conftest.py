"""Shared fixtures: the real dataset (loaded once) and a tiny hand-made frame."""

import pandas as pd
import pytest

from kc_house.data import load_raw, make_training_split


@pytest.fixture(scope="session")
def raw_data() -> pd.DataFrame:
    return load_raw()


@pytest.fixture(scope="session")
def split(raw_data: pd.DataFrame):
    return make_training_split(raw_data)


@pytest.fixture
def tiny_frame() -> pd.DataFrame:
    """Three houses covering the cases the cleaning rules care about."""
    return pd.DataFrame(
        {
            "bedrooms": [3, 33, 4],
            "sqft_living": [1800, 1620, 2400],
            "sqft_above": [1500, 1620, 2400],
            "sqft_basement": ["300.0", "?", "0.0"],
            "view": [None, 2.0, 0.0],
            "waterfront": [None, 0.0, 1.0],
            "yr_built": [1950, 1990, 2005],
            "yr_renovated": [None, 0.0, 2012.0],
            "lat": [47.60, 47.50, 47.65],
            "long": [-122.30, -122.20, -122.25],
        }
    )
