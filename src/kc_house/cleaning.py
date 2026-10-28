"""Data cleaning as small pure functions: each returns a new frame."""

import pandas as pd

from kc_house.config import IMPLAUSIBLE_BEDROOMS


def require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    """Fail early, with the column names, if the input lacks required columns."""
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def drop_implausible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove the 33-bedroom record. Training data only, never used at inference."""
    require_columns(frame, ["bedrooms"])
    return frame.loc[frame["bedrooms"] != IMPLAUSIBLE_BEDROOMS]


def fix_sqft_basement(frame: pd.DataFrame) -> pd.DataFrame:
    """Rebuild basement area as living area minus above-ground area.

    The raw column is text because some rows hold ``?``.
    """
    require_columns(frame, ["sqft_living", "sqft_above"])
    return frame.assign(sqft_basement=frame["sqft_living"] - frame["sqft_above"])


def impute_view_and_waterfront(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill missing ``view`` and ``waterfront`` with 0, their dominant value."""
    require_columns(frame, ["view", "waterfront"])
    return frame.assign(
        view=frame["view"].fillna(0), waterfront=frame["waterfront"].fillna(0)
    )


def add_last_known_change(frame: pd.DataFrame) -> pd.DataFrame:
    """Combine build and renovation year into one feature.

    Uses the renovation year when there is one, else the build year. The two
    source columns are dropped.
    """
    require_columns(frame, ["yr_built", "yr_renovated"])
    renovated = frame["yr_renovated"]
    never_renovated = renovated.isna() | (renovated == 0)
    last_change = frame["yr_built"].where(never_renovated, renovated).astype("int64")
    return frame.assign(last_known_change=last_change).drop(
        columns=["yr_renovated", "yr_built"]
    )


def clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply every cleaning step that is safe at both training and inference."""
    frame = fix_sqft_basement(frame)
    frame = impute_view_and_waterfront(frame)
    return add_last_known_change(frame)
