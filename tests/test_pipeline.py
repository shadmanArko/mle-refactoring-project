import pandas as pd
import pytest
import skops.io as sio
from sklearn.base import clone
from sklearn.pipeline import Pipeline

from kc_house.pipeline import build_model_pipeline


@pytest.fixture(scope="module")
def fitted(split):
    X_train, _, y_train, _ = split
    return build_model_pipeline().fit(X_train, y_train)


def test_pipeline_predicts_straight_from_raw_columns(fitted, split):
    _, X_test, _, y_test = split

    predictions = fitted.predict(X_test.head(5))

    assert predictions.shape == (5,)
    assert (predictions > 0).all()
    assert predictions.mean() == pytest.approx(y_test.head(5).mean(), rel=0.5)


def test_pipeline_can_be_cloned_for_cross_validation():
    pipeline = build_model_pipeline()

    copy = clone(pipeline)

    assert isinstance(copy, Pipeline)
    assert copy.get_params()["model__regressor__alpha"] == 0.01


def test_a_missing_input_column_fails_with_its_name(fitted, split):
    _, X_test, _, _ = split

    with pytest.raises(ValueError, match="lat"):
        fitted.predict(X_test.head(3).drop(columns=["lat"]))


def test_pipeline_survives_a_skops_round_trip(fitted, split):
    """The deployed API loads the model this way, so prove it early."""
    _, X_test, _, _ = split
    payload = sio.dumps(fitted)

    restored = sio.loads(payload, trusted=sio.get_untrusted_types(data=payload))

    pd.testing.assert_series_equal(
        pd.Series(fitted.predict(X_test.head(20))),
        pd.Series(restored.predict(X_test.head(20))),
    )
