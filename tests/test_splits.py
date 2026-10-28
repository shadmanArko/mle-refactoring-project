import pandas as pd
import pytest

from kc_house.data import make_grouped_split, make_temporal_split, make_training_split


def test_grouped_split_never_puts_one_house_on_both_sides(raw_data):
    X_train, X_test, _, _ = make_grouped_split(raw_data)

    assert set(X_train["id"]).isdisjoint(set(X_test["id"]))


def test_temporal_split_trains_on_the_past_and_tests_on_the_future(raw_data):
    X_train, X_test, _, _ = make_temporal_split(raw_data)

    last_train = pd.to_datetime(X_train["date"], format="%m/%d/%Y").max()
    first_test = pd.to_datetime(X_test["date"], format="%m/%d/%Y").min()
    assert last_train <= first_test


@pytest.mark.parametrize(
    "make_split", [make_training_split, make_grouped_split, make_temporal_split]
)
def test_every_split_is_roughly_70_30_without_leaking_the_target(raw_data, make_split):
    X_train, X_test, y_train, y_test = make_split(raw_data)

    assert len(X_train) == len(y_train)
    assert len(X_test) == len(y_test)
    assert len(X_test) / (len(X_train) + len(X_test)) == pytest.approx(0.3, abs=0.02)
    assert "price" not in X_train.columns
    assert set(X_train.index).isdisjoint(set(X_test.index))
