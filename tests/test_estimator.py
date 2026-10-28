import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline

from kc_house.config import ESTIMATE_INPUTS
from kc_house.estimator import ZipcodeDefaults, build_estimator
from kc_house.pipeline import build_preprocessing


@pytest.fixture(scope="module")
def defaults(split) -> ZipcodeDefaults:
    X_train, _, _, _ = split
    return ZipcodeDefaults().fit(X_train)


def answers(**overrides) -> pd.DataFrame:
    row = {
        "bedrooms": 3,
        "bathrooms": 2.0,
        "sqft_living": 1800,
        "grade": 7,
        "zipcode": 98103,
        "waterfront": 0,
    }
    return pd.DataFrame([row | overrides])


def test_six_answers_become_a_complete_raw_record(defaults):
    completed = defaults.transform(answers())

    preprocessed = build_preprocessing().steps[0][1].transform(completed)
    assert preprocessed["sqft_basement"].iloc[0] == 0
    assert completed["sqft_above"].iloc[0] == 1800
    assert {"lat", "long", "sqft_lot", "yr_built", "yr_renovated"} <= set(
        completed.columns
    )


def test_filled_location_is_typical_for_the_zipcode(defaults):
    seattle = defaults.transform(answers(zipcode=98103))
    far_out = defaults.transform(answers(zipcode=98038))

    assert 47.6 < seattle["lat"].iloc[0] < 47.7
    assert far_out["lat"].iloc[0] < 47.45


def test_user_answers_are_kept_untouched(defaults):
    completed = defaults.transform(answers(bedrooms=5, waterfront=1))

    assert completed["bedrooms"].iloc[0] == 5
    assert completed["waterfront"].iloc[0] == 1


def test_unknown_zipcode_is_rejected_with_its_value(defaults):
    with pytest.raises(ValueError, match="12345"):
        defaults.transform(answers(zipcode=12345))


def test_unknown_zipcode_can_fall_back_to_overall_medians_for_cross_validation(split):
    X_train, _, _, _ = split
    lenient = ZipcodeDefaults(unknown="global").fit(X_train)

    completed = lenient.transform(answers(zipcode=12345))

    assert completed["lat"].iloc[0] == pytest.approx(X_train["lat"].median())


def test_missing_answers_name_the_missing_column(defaults):
    with pytest.raises(ValueError, match="grade"):
        defaults.transform(answers().drop(columns=["grade"]))


def test_defaults_are_learned_from_the_rows_given_to_fit(split):
    X_train, _, _, _ = split
    first_half = X_train.iloc[: len(X_train) // 2]

    fitted = ZipcodeDefaults().fit(first_half)

    assert set(fitted.zipcodes_) == set(first_half["zipcode"])


def test_the_estimator_learns_from_the_same_zip_filled_rows_it_will_see_when_serving(
    split,
):
    """ADR-0004: training rows are degraded the same way as serving rows."""
    X_train, _, y_train, _ = split
    full_model = Pipeline(
        [
            ("preprocess", build_preprocessing()),
            ("model", HistGradientBoostingRegressor(max_iter=20, random_state=0)),
        ]
    )
    estimator = build_estimator(full_model).fit(X_train, y_train)

    seen_by_the_model = estimator.named_steps["defaults"].transform(X_train.head(50))

    # The true latitude and the true above-ground area are NOT what the model sees.
    assert not (seen_by_the_model["lat"] == X_train.head(50)["lat"]).all()
    assert (seen_by_the_model["sqft_above"] == seen_by_the_model["sqft_living"]).all()
    assert (X_train.head(50)["sqft_above"] != X_train.head(50)["sqft_living"]).any()


def test_a_six_answer_house_gets_a_plausible_price(split):
    X_train, _, y_train, _ = split
    full_model = Pipeline(
        [
            ("preprocess", build_preprocessing()),
            ("model", HistGradientBoostingRegressor(max_iter=20, random_state=0)),
        ]
    )
    estimator = build_estimator(full_model).fit(X_train, y_train)

    prediction = estimator.predict(answers())

    assert prediction.shape == (1,)
    assert 100_000 < prediction[0] < 2_000_000
    assert list(answers().columns) == ESTIMATE_INPUTS
