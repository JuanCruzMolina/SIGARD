"""Controles de calidad y seguridad con registros y geometrías ficticios."""

from datetime import date, datetime, time
import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from sigard_ml.official.geography import inspect_coordinates, load_capital_boundary
from sigard_ml.official.normalization import parse_coordinate, parse_date
from sigard_ml.official.reports import safe_quality, export_normalized
from sigard_ml.official.validation import inspect_duplicates, validate_sheet


@pytest.mark.parametrize("value,expected", [(None, "missing"), (" ", "missing"),
    ("31/02/2024", "invalid_format"), (45000, "invalid_format"),
    ("2024-01-07", "valid"), ("07/01/2024", "valid"),
    (datetime(2024, 1, 7), "valid"), (date(2024, 1, 7), "valid"),
    ("01/01/1800", "out_of_range")])
def test_dates_are_conservative(value, expected):
    parsed, status = parse_date(value)
    assert status == expected
    if expected == "valid":
        assert parsed == date(2024, 1, 7)


@pytest.mark.parametrize("value,status", [(None, "missing"), ("", "missing"),
    ("bad", "invalid_format"), ("-29,5", "parsed"), ("nan", "invalid_format"),
    ("inf", "invalid_format"), (True, "invalid_format"), ("1,234,567", "invalid_format")])
def test_coordinate_formats(value, status):
    assert parse_coordinate(value)[1] == status


def test_geographic_controls_do_not_assign_or_correct_axes():
    boundary = box(-10, 20, -8, 22)  # Geometría enteramente ficticia.
    original_latitudes = [21, 50, -9, 20, None, 100, "bad", 21]
    original_longitudes = [-9, 50, 21, -10, None, 0, 0, -9]
    rows, report = inspect_coordinates(original_latitudes, original_longitudes, boundary=boundary)
    # Sólo dos pares válidos caen fuera; el par fuera del rango global se
    # informa aparte y el punto del límite queda marcado, sin adjudicar radio.
    assert report["outside_capital_provisional"] == 2
    assert report["possible_axis_inversion"] == 1
    assert report["on_capital_boundary_provisional"] == 1
    assert report["repeated_coordinate_rows"] == 2
    assert report["missing"] == 1 and report["invalid_format"] == 1
    assert report["out_of_global_range"] == 1
    assert rows[2]["latitude_candidate"] == -9 and rows[2]["longitude_candidate"] == 21
    assert not report["territorial_assignment_performed"] and not report["crs_confirmed"]
    assert original_latitudes[2] == -9


def test_no_boundary_does_not_report_false_healthy_zeros():
    _, report = inspect_coordinates([21], [-9])
    assert report["outside_capital_provisional"] is None
    assert report["possible_axis_inversion"] is None


def test_cartography_contract_rejects_invalid_universe(tmp_path):
    path = tmp_path / "fictional.geojson"
    gpd.GeoDataFrame({"radio_id": ["000000001"]}, geometry=[box(0, 0, 1, 1)], crs=4326).to_file(path)
    with pytest.raises(ValueError):
        load_capital_boundary(path)


def test_duplicate_and_update_signals_preserve_all_rows():
    frame = pd.DataFrame({"id": ["fictional-event", "fictional-event", "other", "other"],
                          "value": [1, 2, 3, 3]})
    before = frame.copy(deep=True)
    exact, repeated, report = inspect_duplicates(frame, frame.id.tolist())
    assert exact == [False, False, True, True]
    assert repeated == [True, True, True, True]
    assert report["nonidentical_repeated_event_id_groups"] == 1
    assert report["deduplication_performed"] is False
    pd.testing.assert_frame_equal(before, frame)


def fictional_frame():
    return pd.DataFrame({"c1": ["secret-fictional-event", "secret-fictional-event", None],
                         "c2": ["FICTIONAL_CLASS_A", "FICTIONAL_CLASS_B", None],
                         "c3": ["07/01/2024", "bad-date", None],
                         "c4": ["-29,4", None, "bad-lat"], "c5": [-66.8, None, 999],
                         "c6": ["FICTIONAL_PERSON", "FICTIONAL_PERSON", None]}, index=[2, 3, 4])


def test_quality_projection_excludes_identifiers_and_marks_unresolved_records(tmp_path):
    frame = fictional_frame()
    fields = {"event_id": "c1", "classification": "c2", "symptom_onset": "c3",
              "latitude": "c4", "longitude": "c5", "given_name": "c6"}
    normalized, report, identifiers = validate_sheet(frame, {"fields": fields, "columns": 6, "header_row": 1},
        source_id="fixture", source_hash="fixture-hash", as_of=date(2024, 12, 31))
    assert len(normalized) == len(frame) == 3
    assert report["structurally_complete"] == 1
    assert report["incomplete_or_invalid"] == 2
    assert report["methodology_review_required"] == 3
    assert report["dates"]["symptom_onset"]["invalid_format"] == 1
    assert not report["case_eligibility_determined"]
    assert "FICTIONAL_CLASS" not in json.dumps(report)
    assert "secret-fictional-event" not in str(identifiers)
    assert "FICTIONAL_PERSON" not in normalized.to_json()
    assert "secret-fictional-event" not in normalized.to_json()
    export_normalized(normalized, tmp_path, "fixture", "sheet_01")
    saved = pd.read_parquet(tmp_path / "fixture_sheet_01.parquet")
    assert saved.record_ref.tolist() == normalized.record_ref.tolist()
    assert "given_name" not in saved and "event_id" not in saved


def test_missing_columns_are_reported_and_prevent_structural_completeness():
    normalized, report, _ = validate_sheet(pd.DataFrame({"unknown": [1, 2]}),
        {"fields": {}, "columns": 1, "header_row": 1}, source_id="fixture", source_hash="fixture",
        as_of=date(2024, 1, 1))
    assert len(report["missing_required_columns"]) == 5
    assert report["structurally_complete"] == 0
    assert not normalized.structurally_complete.any()


def test_safe_report_suppresses_small_counts_and_retains_structural_years():
    safe = safe_quality({"rows": 3, "invalid_format": 1, "missing": 0, "columns": 3,
                         "header_row": 1, "period_year_min": 2024})
    assert safe == {"rows": "<5", "invalid_format": "<5", "missing": 0,
                    "columns": 3, "header_row": 1, "period_year_min": 2024}


def test_future_dates_and_sample_before_symptoms_are_review_flags():
    frame = pd.DataFrame({"id": ["fixture-1", "fixture-2"], "class": ["Sospechoso", "Confirmado"],
                          "symptoms": [date(2030, 1, 1), date(2024, 1, 7)],
                          "sample": [date(2024, 1, 1), date(2024, 1, 6)]})
    _, report, _ = validate_sheet(frame, {"fields": {"event_id": "id", "classification": "class",
        "symptom_onset": "symptoms", "sample_on": "sample"}, "columns": 4, "header_row": 1},
        source_id="fixture", source_hash="fixture", as_of=date(2024, 12, 31))
    assert report["dates"]["symptom_onset"]["future"] == 1
    assert report["sample_before_symptoms_needs_review"] == 2
    assert report["classification_literal_labels"] == {"suspected_label": 1, "confirmed_label": 1}


def test_time_without_date_is_never_assigned_a_fictional_day():
    from sigard_ml.official.excel import value_type
    assert value_type(time(0, 0)) == "time_without_date"
    assert parse_date(time(0, 0)) == (None, "invalid_format")
