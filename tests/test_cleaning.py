import pandas as pd
import pytest

from kc_house.cleaning import (
    add_last_known_change,
    clean,
    drop_implausible_rows,
    fix_sqft_basement,
    impute_view_and_waterfront,
    require_columns,
)


def test_drop_implausible_rows_removes_only_the_33_bedroom_house(tiny_frame):
    result = drop_implausible_rows(tiny_frame)

    assert list(result["bedrooms"]) == [3, 4]


def test_fix_sqft_basement_replaces_question_marks_with_numbers(tiny_frame):
    result = fix_sqft_basement(tiny_frame)

    assert list(result["sqft_basement"]) == [300, 0, 0]
    assert pd.api.types.is_numeric_dtype(result["sqft_basement"])


def test_impute_fills_missing_view_and_waterfront_with_zero(tiny_frame):
    result = impute_view_and_waterfront(tiny_frame)

    assert result.loc[0, "view"] == 0
    assert result.loc[0, "waterfront"] == 0
    assert result.loc[2, "waterfront"] == 1


@pytest.mark.parametrize(
    ("renovated", "expected"),
    [(None, 1950), (0.0, 1950), (1991.0, 1991)],
    ids=["missing", "zero", "renovated"],
)
def test_last_known_change_prefers_renovation_year(renovated, expected):
    frame = pd.DataFrame({"yr_built": [1950], "yr_renovated": [renovated]})

    result = add_last_known_change(frame)

    assert result.loc[0, "last_known_change"] == expected
    assert result["last_known_change"].dtype == "int64"


def test_last_known_change_drops_source_columns(tiny_frame):
    result = add_last_known_change(tiny_frame)

    assert "yr_built" not in result.columns
    assert "yr_renovated" not in result.columns


def test_cleaning_never_mutates_its_input(tiny_frame):
    before = tiny_frame.copy(deep=True)

    clean(tiny_frame)
    drop_implausible_rows(tiny_frame)

    pd.testing.assert_frame_equal(tiny_frame, before)


def test_missing_columns_raise_a_helpful_error():
    with pytest.raises(ValueError, match="sqft_above"):
        require_columns(pd.DataFrame({"sqft_living": [1]}), ["sqft_above"])
