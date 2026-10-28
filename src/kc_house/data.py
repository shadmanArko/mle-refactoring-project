"""Loading the raw data and the three ways we split it."""

from pathlib import Path
from typing import cast

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from kc_house.cleaning import drop_implausible_rows
from kc_house.config import DEFAULT_DATA_PATH, RANDOM_STATE, TARGET, TEST_SIZE

Split = tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]


def load_raw(path: Path = DEFAULT_DATA_PATH) -> pd.DataFrame:
    """Read the raw CSV unchanged."""
    return pd.read_csv(path)


def _features_and_target(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    frame = drop_implausible_rows(raw)
    return frame.drop(columns=[TARGET]), frame[TARGET]


def make_training_split(raw: pd.DataFrame) -> Split:
    """Drop implausible rows, then split 70/30 randomly with the notebook's seed.

    Returns ``X_train, X_test, y_train, y_test``. ``X`` keeps all raw columns
    except the target; the pipeline picks what it needs.
    """
    features, target = _features_and_target(raw)
    split = train_test_split(
        features, target, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    # scikit-learn types its splits loosely; with DataFrame/Series in, these come out.
    return cast(Split, tuple(split))


def make_grouped_split(raw: pd.DataFrame) -> Split:
    """Like the random split, but a house ``id`` never appears on both sides.

    177 houses were sold twice; a random split can train on one sale and test on
    the other, which flatters the score.
    """
    features, target = _features_and_target(raw)
    splitter = GroupShuffleSplit(
        n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    train_rows, test_rows = next(
        splitter.split(features, target, groups=features["id"])
    )
    return (
        features.iloc[train_rows],
        features.iloc[test_rows],
        target.iloc[train_rows],
        target.iloc[test_rows],
    )


def make_temporal_split(raw: pd.DataFrame) -> Split:
    """Train on the earliest 70% of sales, test on the latest 30%.

    Mirrors real use: the model is trained on the past and asked about the future.
    """
    features, target = _features_and_target(raw)
    sale_date = pd.to_datetime(features["date"], format="%m/%d/%Y")
    ordered = sale_date.sort_values(kind="stable").index
    cut = int(len(ordered) * (1 - TEST_SIZE))
    train_index, test_index = ordered[:cut], ordered[cut:]
    return (
        features.loc[train_index],
        features.loc[test_index],
        target.loc[train_index],
        target.loc[test_index],
    )
