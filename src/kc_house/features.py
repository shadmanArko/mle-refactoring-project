"""Feature engineering: stateless functions and one fitted transformer."""

from typing import Self

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from kc_house.cleaning import require_columns
from kc_house.config import (
    CENTER_COS_LAT,
    CENTER_LAT,
    CENTER_LONG,
    KM_PER_DEGREE,
    MODEL_FEATURES,
)


def add_center_distance(frame: pd.DataFrame) -> pd.DataFrame:
    """Distance in km from each house to the "centre of wealth" reference point."""
    require_columns(frame, ["lat", "long"])
    delta_lat = (CENTER_LAT - frame["lat"]).abs()
    delta_long = (CENTER_LONG - frame["long"]).abs()
    km = np.hypot(delta_long * np.cos(np.radians(CENTER_COS_LAT)), delta_lat)
    return frame.assign(center_distance=km * KM_PER_DEGREE)


def select_model_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep exactly the model's input columns, in the model's order."""
    require_columns(frame, MODEL_FEATURES)
    return frame.loc[:, MODEL_FEATURES]


class WaterDistance(BaseEstimator, TransformerMixin):
    """Distance in km to the nearest waterfront house seen during ``fit``.

    The reference points are learned from the data passed to ``fit`` only, so
    validation and test rows can never influence a training feature.
    """

    def __init__(self, chunk_size: int = 2000) -> None:
        self.chunk_size = chunk_size

    def fit(self, X: pd.DataFrame, y: object = None) -> Self:
        require_columns(X, ["waterfront", "lat", "long"])
        reference = X.loc[X["waterfront"] == 1, ["lat", "long"]]
        if reference.empty:
            raise ValueError("Cannot fit WaterDistance: no waterfront houses in X.")
        self.reference_lat_ = reference["lat"].to_numpy(dtype=float)
        self.reference_long_ = reference["long"].to_numpy(dtype=float)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        require_columns(X, ["lat", "long"])
        lat = X["lat"].to_numpy(dtype=float)
        long = X["long"].to_numpy(dtype=float)
        # Longitude shrinks with latitude, so each reference point has its own cosine.
        cos_ref = np.cos(np.radians(self.reference_lat_))
        nearest = np.empty(len(X))
        for start in range(0, len(X), self.chunk_size):
            rows = slice(start, start + self.chunk_size)
            delta_lat = lat[rows, None] - self.reference_lat_[None, :]
            delta_long = (long[rows, None] - self.reference_long_[None, :]) * cos_ref
            nearest[rows] = (np.hypot(delta_long, delta_lat) * KM_PER_DEGREE).min(
                axis=1
            )
        return X.assign(water_distance=nearest)
