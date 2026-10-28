"""Loading the raw data and splitting it the way the notebook does."""

from pathlib import Path
from typing import cast

import pandas as pd
from sklearn.model_selection import train_test_split

from kc_house.cleaning import drop_implausible_rows
from kc_house.config import DEFAULT_DATA_PATH, RANDOM_STATE, TARGET, TEST_SIZE


def load_raw(path: Path = DEFAULT_DATA_PATH) -> pd.DataFrame:
    """Read the raw CSV unchanged."""
    return pd.read_csv(path)


def make_training_split(
    raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Drop implausible rows, then split 70/30 with the notebook's seed.

    Returns ``X_train, X_test, y_train, y_test``. ``X`` keeps all raw columns
    except the target; the pipeline picks what it needs.
    """
    frame = drop_implausible_rows(raw)
    features = frame.drop(columns=[TARGET])
    split = train_test_split(
        features, frame[TARGET], test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    # scikit-learn types its splits loosely; with DataFrame/Series in, these come out.
    return cast(tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series], tuple(split))
