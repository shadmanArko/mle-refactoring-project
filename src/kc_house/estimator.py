"""The six-question estimator: a few answers in, a price out.

A visitor cannot type 19 columns. ``ZipcodeDefaults`` turns six answers into the
full set of raw columns by filling the unknown ones with what is typical for the
house's zip code, learned from training data only.
"""

from typing import Self

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.pipeline import Pipeline

from kc_house.cleaning import require_columns
from kc_house.config import ESTIMATE_INPUTS

# Columns filled with the zip code's median value.
ZIP_MEDIAN_COLUMNS = [
    "sqft_lot",
    "floors",
    "condition",
    "view",
    "yr_built",
    "lat",
    "long",
    "sqft_living15",
    "sqft_lot15",
]


class ZipcodeDefaults(BaseEstimator, TransformerMixin):
    """Complete a six-answer house into a full raw record.

    * ``fit`` learns the median of each unknown column per zip code (training rows).
    * ``transform`` needs only the six answers; it assumes no basement and no
      renovation, since the visitor was not asked.

    Medians are kept as plain arrays so the fitted object saves cleanly with skops.
    """

    def fit(self, X: pd.DataFrame, y: object = None) -> Self:
        require_columns(X, [*ESTIMATE_INPUTS, *ZIP_MEDIAN_COLUMNS])
        medians = X.groupby("zipcode")[ZIP_MEDIAN_COLUMNS].median()
        self.zipcodes_ = medians.index.to_numpy(dtype=np.int64)
        self.medians_ = medians.to_numpy(dtype=float)
        self.median_columns_ = list(ZIP_MEDIAN_COLUMNS)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        require_columns(X, ESTIMATE_INPUTS)
        positions = np.searchsorted(self.zipcodes_, X["zipcode"].to_numpy())
        positions = np.clip(positions, 0, len(self.zipcodes_) - 1)
        unknown = X["zipcode"].to_numpy() != self.zipcodes_[positions]
        if unknown.any():
            bad = sorted({int(z) for z in X["zipcode"].to_numpy()[unknown]})
            raise ValueError(f"Unknown zipcode(s): {bad}")

        completed = X[ESTIMATE_INPUTS].copy()
        for column, values in zip(
            self.median_columns_, self.medians_[positions].T, strict=True
        ):
            completed[column] = values
        completed["sqft_above"] = completed["sqft_living"]  # no basement assumed
        completed["yr_renovated"] = 0.0  # never renovated assumed
        return completed


def build_estimator(full_model: Pipeline) -> Pipeline:
    """Wrap an unfitted full model so it can answer from six questions."""
    return Pipeline([("defaults", ZipcodeDefaults()), ("model", clone(full_model))])
