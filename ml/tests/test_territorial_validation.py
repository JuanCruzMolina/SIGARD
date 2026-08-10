import pandas as pd
import pytest

from sigard_ml.validation.territorial import (
    TerritorialValidationError,
    compare_id_sets,
    normalize_code,
    validate_one_to_one_sources,
)


def test_normalize_code_preserves_and_adds_leading_zeroes() -> None:
    values = pd.Series(["01", "2"], dtype="string")
    assert normalize_code(values, 2, "radio").tolist() == ["01", "02"]


@pytest.mark.parametrize("value", ["", None, "A1", "123"])
def test_normalize_code_rejects_invalid_values(value: object) -> None:
    with pytest.raises(TerritorialValidationError):
        normalize_code(pd.Series([value], dtype="string"), 2, "radio")


def test_compare_id_sets_reports_both_directions_sorted() -> None:
    assert compare_id_sets(["002", "001"], ["003", "002"]) == {
        "missing_from_source": ["001"],
        "not_in_cartography": ["003"],
    }


def test_validate_one_to_one_sources_accepts_exact_match() -> None:
    cartography = pd.DataFrame({"radio_id": ["001", "002"]})
    source = pd.DataFrame({"radio_id": ["002", "001"], "count": [2, 1]})
    report = validate_one_to_one_sources(cartography, {"population": source})
    assert report["all_sources_one_to_one"] is True
    assert report["sources"]["population"]["one_to_one"] is True


def test_validate_one_to_one_sources_rejects_duplicates_and_missing_ids() -> None:
    cartography = pd.DataFrame({"radio_id": ["001", "002"]})
    source = pd.DataFrame({"radio_id": ["001", "001"]})
    with pytest.raises(TerritorialValidationError):
        validate_one_to_one_sources(cartography, {"population": source})
