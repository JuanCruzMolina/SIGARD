"""Fixtures completamente ficticios; no abre fuentes ni artefactos del MVP."""

from dataclasses import asdict, replace
from datetime import date
import json
from pathlib import Path

import pytest

from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.calendar import make_week
from sigard_ml.official.contracts import (
    AssignmentStatus, ContractError, Coordinates, DataKind, DatasetMetadata,
    Eligibility, EpidemiologicalRecord, EvaluationMode, FeatureValue, LocationRole,
    ObservationStatus, ObservedPanel, ObservedRadioWeek, QualityCode, QualityReport,
    RecordUnit, Target, TerritorialAssignment, TerritorialPrediction,
    TrainingDataset, TrainingExample,
)


@pytest.fixture
def metadata():
    return DatasetMetadata("fixture-panel-v1", DataKind.FICTIONAL_FIXTURE,
                           ("fixture-source-v1",), "fixture-transform-v1",
                           date(2023, 12, 31), date(2024, 1, 20), "fixture-cartography-v1")


@pytest.fixture
def source(tmp_path):
    # Esta ruta jamás se crea ni se abre. No representa ninguno de los cinco Excel.
    return SourceAuthorization("fixture-source", "fixture-v1", tmp_path / "fictional.xlsx",
                               ("fictional-sheet",), "fictional-extract")


def approved(source):
    return replace(source, enabled=True, approved_extract=True,
                   uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
                   evidence_ref="fixture-permit", custodian_ref="fixture-custodian",
                   confidentiality_ref="fixture-confidentiality", storage_policy_ref="fixture-storage")


def authorize(source, **changes):
    arguments = {"sheet": "fictional-sheet", "subset_ref": "fictional-extract",
                 "use": AuthorizedUse.INSPECTION}
    arguments.update(changes)
    return SourceRegistry((source,)).authorize("fixture-source", **arguments)


def test_registry_denies_unknown_source_and_defaults(source):
    with pytest.raises(AccessDenied):
        SourceRegistry().authorize("unknown", sheet="fictional-sheet",
                                   subset_ref="fictional-extract", use=AuthorizedUse.INSPECTION)
    with pytest.raises(AccessDenied):
        authorize(source)
    assert not source.path.exists()


@pytest.mark.parametrize("field", ["enabled", "approved_extract", "evidence_ref",
                                  "custodian_ref", "confidentiality_ref", "storage_policy_ref"])
def test_each_permission_requirement_is_mandatory(source, field):
    value = False if field in ("enabled", "approved_extract") else None
    with pytest.raises(AccessDenied):
        authorize(replace(approved(source), **{field: value}))


@pytest.mark.parametrize("changes", [{"sheet": "other-sheet"}, {"subset_ref": "pending-extract"},
                                     {"use": AuthorizedUse.TRAINING}, {"use": AuthorizedUse.EVALUATION},
                                     {"use": AuthorizedUse.PUBLICATION}, {"use": "inspection"}])
def test_permission_is_specific_to_sheet_subset_and_use(source, changes):
    with pytest.raises(AccessDenied):
        authorize(approved(source), **changes)


def test_authorization_is_only_an_in_memory_gate(source):
    permission = approved(source)
    assert authorize(permission) is permission
    assert not source.path.exists()
    assert str(source.path) not in repr(permission)
    with pytest.raises(ContractError):
        SourceRegistry((permission, permission))
    with pytest.raises(ContractError):
        replace(permission, sheets=("*",))
    with pytest.raises(ContractError):
        replace(permission, path=Path("relative.xlsx"))


def test_permission_checks_never_probe_or_open_the_source(source, monkeypatch):
    def forbidden_io(*args, **kwargs):
        pytest.fail("La autorización no debe acceder al filesystem")

    monkeypatch.setattr(Path, "open", forbidden_io)
    monkeypatch.setattr(Path, "stat", forbidden_io)
    monkeypatch.setattr(Path, "resolve", forbidden_io)
    permission = approved(source)
    assert authorize(permission) is permission
    with pytest.raises(AccessDenied):
        authorize(source)


@pytest.mark.parametrize("year,number,start", [(2024, 1, date(2023, 12, 31)),
                                              (2024, 52, date(2024, 12, 22)),
                                              (2020, 53, date(2020, 12, 27))])
def test_calendar_reuses_existing_convention(year, number, start):
    assert make_week(year, number).start == start


@pytest.mark.parametrize("year,number", [(2024, 53), (2024, 0), (2024, 54),
                                         (True, 1), (2024, True), (2024, 1.5)])
def test_calendar_rejects_invalid_or_nonexistent_weeks(year, number):
    with pytest.raises(ContractError):
        make_week(year, number)


def test_week_rejects_inconsistent_year_number_and_dates():
    week = make_week(2024, 1)
    for change in ({"year": 2023}, {"number": 2}, {"start": date(2024, 1, 1)},
                   {"end": date(2024, 1, 5)}, {"convention": "ISO"}):
        with pytest.raises(ContractError):
            replace(week, **change)


def test_metadata_excludes_legacy_synthetic_data(metadata):
    assert metadata.data_kind == DataKind.FICTIONAL_FIXTURE
    for change in ({"data_kind": "synthetic"}, {"source_versions": ()},
                   {"period_end": date(2020, 1, 1)}, {"unit": "department_week"},
                   {"schema_version": "unsupported"}):
        with pytest.raises(ContractError):
            replace(metadata, **change)


@pytest.mark.parametrize("x,y", [(181, 0), (0, 91), (float("nan"), 0), (0, float("inf")), (True, 0)])
def test_coordinates_reject_invalid_values_without_echoing_them(x, y):
    with pytest.raises(ContractError) as error:
        Coordinates(x, y, "EPSG:4326", LocationRole.RESIDENCE)
    assert "181" not in str(error.value)


def test_record_semantics_are_not_assumed():
    coordinate = Coordinates(0.25, 0.25, "EPSG:4326", LocationRole.RESIDENCE)
    record = EpidemiologicalRecord("opaque-fixture-1", "fixture-source", "fixture-v1",
                                   RecordUnit.UNKNOWN, Eligibility.UNRESOLVED, "fixture-rule-v1",
                                   None, None, coordinate)
    assert "opaque-fixture-1" not in repr(record)
    assert "0.25" not in repr(coordinate)
    with pytest.raises(ContractError):
        replace(record, eligibility=Eligibility.ELIGIBLE_EPISODE)
    eligible = replace(record, record_unit=RecordUnit.EPISODE, eligibility=Eligibility.ELIGIBLE_EPISODE)
    assert eligible.coordinates.role == LocationRole.RESIDENCE


@pytest.mark.parametrize("status", list(AssignmentStatus))
def test_assignment_requires_valid_radio_only_for_unambiguous_assignment(status):
    assignment = TerritorialAssignment("opaque-fixture-1", status, "fixture-map-v1",
                                       "000000001" if status == AssignmentStatus.ASSIGNED else None)
    assert "opaque-fixture-1" not in repr(assignment)
    with pytest.raises(ContractError):
        replace(assignment, radio_id=None if status == AssignmentStatus.ASSIGNED else "000000001")


@pytest.mark.parametrize("status,count", [(ObservationStatus.OBSERVED, 3),
                                         (ObservationStatus.EXPLICIT_ZERO, 0),
                                         (ObservationStatus.MISSING, None),
                                         (ObservationStatus.OUTSIDE_COVERAGE, None)])
def test_observation_preserves_zeros_and_absences(status, count):
    row = ObservedRadioWeek("000000001", make_week(2024, 1), count, status, None)
    assert row.observed_cases == count


@pytest.mark.parametrize("status,count", [(ObservationStatus.MISSING, 0),
                                         (ObservationStatus.OUTSIDE_COVERAGE, 0),
                                         (ObservationStatus.OBSERVED, 0),
                                         (ObservationStatus.EXPLICIT_ZERO, 1),
                                         (ObservationStatus.OBSERVED, -1),
                                         (ObservationStatus.OBSERVED, 1.5),
                                         (ObservationStatus.OBSERVED, True)])
def test_observation_rejects_invalid_counts_and_status(status, count):
    with pytest.raises(ContractError):
        ObservedRadioWeek("000000001", make_week(2024, 1), count, status, 1)


def test_panel_checks_unique_keys_period_and_coverage(metadata):
    row = ObservedRadioWeek("000000001", make_week(2024, 1), 3, ObservationStatus.OBSERVED, 0.5)
    assert ObservedPanel(metadata, (row,)).rows == (row,)
    with pytest.raises(ContractError):
        ObservedPanel(metadata, (row, row))
    with pytest.raises(ContractError):
        ObservedPanel(metadata, (replace(row, week=make_week(2024, 4)),))
    with pytest.raises(ContractError):
        replace(row, geographic_coverage=1.1)


def test_quality_report_has_only_safe_aggregate_fields_and_is_reproducible():
    report = QualityReport(4, 2, ((QualityCode.MISSING_DATE, 1), (QualityCode.POSSIBLE_DUPLICATE, 2)))
    encoded = json.dumps(report.summary(), sort_keys=True)
    reversed_report = QualityReport(4, 2, tuple(reversed(report.issue_counts)))
    assert encoded == json.dumps(reversed_report.summary(), sort_keys=True)
    assert set(asdict(report)) == {"inspected_rows", "accepted_rows", "issue_counts"}
    with pytest.raises(ContractError):
        QualityReport(1, 2)
    with pytest.raises(ContractError):
        QualityReport(2, 1, (("private-free-text", 1),))
    with pytest.raises(ContractError):
        QualityReport(2, 1, ((QualityCode.MISSING_DATE, 1), (QualityCode.MISSING_DATE, 1)))


@pytest.fixture
def training_example():
    feature = FeatureValue("cases_lag_1", 3, date(2024, 1, 5), date(2024, 1, 6))
    return TrainingExample("000000001", date(2024, 1, 6), make_week(2024, 2), 2, (feature,))


def test_training_blocks_future_features_and_wrong_horizon(training_example):
    with pytest.raises(ContractError):
        replace(training_example, features=(replace(training_example.features[0], available_on=date(2024, 1, 7)),))
    with pytest.raises(ContractError):
        replace(training_example.features[0], observed_through=date(2024, 1, 7))
    with pytest.raises(ContractError):
        replace(training_example, target_week=make_week(2024, 3))


@pytest.mark.parametrize("name", ["latitude", "longitude", "dni", "radio_id", "synthetic_cases_assigned", "target_cases_next_week"])
def test_individual_synthetic_and_target_features_are_excluded(training_example, name):
    with pytest.raises(ContractError):
        replace(training_example.features[0], name=name)


def test_training_dataset_requires_a_single_target_and_consistent_schema(metadata, training_example):
    dataset = TrainingDataset(metadata, Target.COUNT, ("cases_lag_1",),
                              (training_example,), EvaluationMode.RETROSPECTIVE)
    assert dataset.target == Target.COUNT
    for change in ({"examples": (training_example, training_example)},
                   {"feature_names": ("population",)}, {"target": "mixed"},
                   {"target": Target.OCCURRENCE},
                   {"examples": (replace(training_example, target_value=2.5),)}):
        with pytest.raises(ContractError):
            replace(dataset, **change)


@pytest.mark.parametrize("target,value,unit", [(Target.COUNT, 2.5, "expected_cases"),
                                              (Target.OCCURRENCE, 0.3, "probability"),
                                              (Target.INCIDENCE, 5, "cases_per_100000_population")])
def test_prediction_units_are_explicit(target, value, unit):
    prediction = TerritorialPrediction("000000001", date(2024, 1, 6), make_week(2024, 2),
                                       target, value, "fixture-model-v1", "fixture-panel-v1",
                                       DataKind.FICTIONAL_FIXTURE)
    assert prediction.unit == unit
    with pytest.raises(ContractError):
        replace(prediction, value=-1)
    if target == Target.OCCURRENCE:
        with pytest.raises(ContractError):
            replace(prediction, value=1.1)
