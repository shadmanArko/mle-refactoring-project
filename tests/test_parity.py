"""The refactor must reproduce the notebook (see ADR-0002)."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kc_house.cleaning import drop_implausible_rows
from kc_house.config import MODEL_FEATURES, TARGET
from kc_house.pipeline import build_model_pipeline, build_preprocessing

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(scope="module")
def golden_frame() -> pd.DataFrame:
    return pd.read_csv(GOLDEN / "clean_frame.csv.gz", index_col=0)


@pytest.fixture(scope="module")
def golden_metrics() -> dict:
    return json.loads((GOLDEN / "baseline_metrics.json").read_text())


def test_model_features_match_the_notebook_column_order(golden_metrics):
    assert ["id", *MODEL_FEATURES] == golden_metrics["feature_columns"]


def test_every_feature_column_matches_the_notebook(raw_data, golden_frame):
    features = drop_implausible_rows(raw_data).drop(columns=[TARGET])

    result = build_preprocessing().fit(features).transform(features)

    assert result.index.equals(golden_frame.index)
    for column in MODEL_FEATURES:
        np.testing.assert_allclose(
            result[column].astype(float),
            golden_frame[column].astype(float),
            rtol=1e-9,
            atol=1e-9,
            err_msg=f"column {column} differs from the notebook",
        )


def test_train_test_split_is_identical_to_the_notebook(split, golden_metrics):
    X_train, X_test, _, _ = split

    digest = hashlib.sha256(",".join(map(str, X_train.index)).encode()).hexdigest()

    assert digest == golden_metrics["train_index_sha256"]
    assert len(X_train) == golden_metrics["x_train_shape"][0]
    assert "price" not in X_train.columns
    assert len(X_test) == golden_metrics["x_test_shape"][0]


def test_final_model_scores_like_the_notebook(split, golden_metrics):
    """Not bit-identical on purpose.

    The notebook computes water_distance from ALL rows before splitting; the
    pipeline learns it from training rows only. The score must stay within a
    hair of the notebook's, showing the leakage fix costs nothing.
    """
    X_train, X_test, y_train, y_test = split

    score = build_model_pipeline().fit(X_train, y_train).score(X_test, y_test)

    assert score == pytest.approx(golden_metrics["elastic_test_r2"], abs=0.005)
