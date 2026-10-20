"""Etapa 7: todos los objetos y referencias son ficticios; sin datos del proyecto."""

from copy import deepcopy
from datetime import date
import io
import json

import pandas as pd
import pytest

from sigard_ml.official.calendar_rules import CALENDAR_VERSION
from sigard_ml.official.classification import classify_labels
from sigard_ml.official.coverage_policy import decide_observation
from sigard_ml.official.episodes import review_episode_groups
from sigard_ml.official.observed_dates import assign_record_weeks, parse_reference_date
from sigard_ml.official.epidemiological_validator import validate_label, validate_records, validate_week
from sigard_ml.official.epidemiological_validator.__main__ import main


def record(**changes):
    row = {"source_id": "fictional_source", "sheet_ref": "fictional_sheet", "record_ref": "fictional_row",
           "event_ref": "fictional_opaque_event", "epidemiological_eligibility_validated": False,
           "calendar_version": CALENDAR_VERSION,
           "assignment_state": "uncertain", "geometry_status": "unique_interior",
           "radio_candidate": "fictional_radio_a", "matching_radios": ["fictional_radio_a"],
           "uncertainty_reasons": ["location_meaning_unknown"], "epidemiological_precision_validated": False,
           "symptom_onset": date(2024, 1, 2), "symptom_onset_status": "valid"}
    row.update(classify_labels(["Fictional mapped label"], {"Fictional mapped label": "confirmado"}, "fictional-map-v1").iloc[0].to_dict())
    row.update(assign_record_weeks(pd.DataFrame([row]), field="symptom_onset", period_start=date(2020, 1, 1),
                                  period_end=date(2024, 12, 31), as_of=date(2024, 12, 31), version="fictional-date-v1").iloc[0].to_dict())
    row.update(review_episode_groups(pd.DataFrame([row]), version="fictional-episode-v1").iloc[0].to_dict())
    row.update(changes)
    for field in ("symptom_onset", "consultation_on", "sample_on", "notified_on"):
        if field in changes and field + "_status" not in changes:
            row[field + "_status"] = parse_reference_date(row[field])[1]
    return row


def week(raw=0, pending=0, declared="unknown", verified="unknown", scenario="conservative", partial=False, **changes):
    observed, coverage, state, provisional = decide_observation(raw, pending, declared, verified, scenario, partial_window=partial)
    row = {"radio_censal": "fictional_radio_a", "calendar_version": CALENDAR_VERSION,
           "anio_epidemiologico": 2024, "semana_epidemiologica": 1,
           "fecha_inicio_semana": "2023-12-31", "fecha_fin_semana": "2024-01-06",
           "registros_elegibles_provisionales": raw, "registros_pendientes_posibles": pending,
           "cobertura_declarada": declared, "cobertura_comprobada": verified,
           "escenario": scenario, "ventana_semanal_parcial": partial, "casos_observados": observed,
           "estado_cobertura": coverage, "estado_observacion": state, "cero_provisional": provisional,
           "version_cobertura": "fictional-coverage-v1",
           "declaracion_cobertura_ref": "fictional-declaration" if declared != "unknown" else None,
           "verificacion_cobertura_ref": "fictional-review" if verified != "unknown" else None,
           "zero_policy": {"enabled": True, "allow_declared_complete_in_exploratory": True}}
    return {**row, **changes}


def label(**changes):
    return {"tipo_etiqueta": "cero_asumido_experimental", "objetivo_semana_siguiente": 0, "objetivo_valido": True,
            "cobertura_asumida_no_verificada": True, "autorizacion_cobertura_ref": "fictional-decision",
            "en_intervalo_autorizado": True, "pendientes_semana_objetivo": 0, "semana_objetivo_parcial": False,
            "conteo_original_semana_objetivo": None, "objetivo_original": None, **changes}


def has(checks, control, status):
    return any(check.control_id == control and check.status == status for check in checks)


def validate(row):
    return validate_records([row])[0]


def test_provisional_classification_is_not_verified_by_confirmed_literal():
    checks = validate(record(classification_label="confirmado"))
    assert has(checks, "classification.state", "advertencia")
    assert not has(checks, "classification.state", "valido")


@pytest.mark.parametrize("category", [None, "indeterminado"])
def test_missing_classification_stays_unknown(category):
    checks = validate(record(classification=category, classification_label="confirmado"))
    assert has(checks, "classification.state", "pendiente_acreditacion")


def test_verified_classification_requires_explicit_decision_reference():
    assert has(validate(record(epidemiological_eligibility_validated=True)), "classification.state", "pendiente_acreditacion")
    assert has(validate(record(epidemiological_eligibility_validated=True, classification_evidence_ref="fictional-reviewed-decision")),
               "classification.state", "valido")
    assert has(validate(record(classification=None, epidemiological_eligibility_validated=True)), "classification.evidence", "invalido")


@pytest.mark.parametrize("changes", [{"classification": "unknown_word"}, {"classification": []},
    {"classification_mapped": False}, {"classification_rule_version": ""}, {"epidemiological_eligibility_validated": "true"}])
def test_classification_structural_contradictions(changes):
    assert any(check.status == "invalido" for check in validate(record(**changes)))


def test_missing_reference_is_not_imputed_from_sample():
    row = record(symptom_onset=None, sample_on="2024-01-02", reference_date=None,
                 week_start=None, week_end=None, epidemiological_year=None, epidemiological_week=None)
    before = deepcopy(row)
    checks = validate(row)
    assert has(checks, "date.reference", "pendiente_acreditacion")
    assert row == before


def test_assigned_week_without_reference_is_invalid():
    assert has(validate(record(reference_date=None)), "date.week", "invalido")


@pytest.mark.parametrize("changes", [{"epidemiological_week": 2}, {"week_start": "2024-01-01"},
    {"week_end": "2024-01-07"}, {"epidemiological_week": 53}, {"epidemiological_year": 2027},
    {"calendar_version": "sigard-iso-shift-v0"}, {"reference_date": "02/01/24"},
    {"reference_date_field": []}, {"symptom_onset": "2024-02-30"}])
def test_inconsistent_dates_and_weeks_are_invalid(changes):
    assert any(check.status == "invalido" for check in validate(record(**changes)))


def test_sample_reference_keeps_approximation_and_does_not_recover_symptom_date():
    row = record(symptom_onset=None, sample_on="2024-01-02", reference_date="2024-01-02",
                 reference_date_field="sample_on", tipo_fecha_referencia="toma_muestra", fecha_aproximada=True)
    checks = validate(row)
    assert has(checks, "date.approximation", "advertencia")
    assert has(checks, "date.symptom_onset", "advertencia")
    assert not any(check.status == "invalido" for check in checks)
    assert has(validate({**row, "fecha_aproximada": False}), "date.approximation", "invalido")


def test_sample_before_symptoms_is_review_signal_not_clinical_invalidation():
    checks = validate(record(sample_on="2024-01-01"))
    assert has(checks, "date.chronology", "advertencia")
    assert not any(check.status == "invalido" for check in checks)


def test_possible_repetition_preserves_rows_and_does_not_choose_episode_representative():
    rows = [record(record_ref="fictional_1", identity_countable=False), record(record_ref="fictional_2", identity_countable=False)]
    before = deepcopy(rows)
    checks = validate_records(rows)
    assert len(checks) == 2
    assert all(has(group, "episode.identity", "pendiente_acreditacion") for group in checks)
    assert rows == before


def test_repeated_technical_key_differs_from_possible_repeated_episode():
    checks = validate_records([record(), record()])
    assert all(has(group, "record.unique_key", "invalido") for group in checks)
    assert all(has(group, "episode.countable", "invalido") for group in checks)


def test_missing_identity_and_incomplete_resolution_are_pending_or_invalid():
    assert has(validate(record(event_ref=None, identity_countable=False)), "episode.identity", "pendiente_acreditacion")
    assert has(validate(record(identity_resolved_by_review=True)), "episode.resolution", "invalido")


@pytest.mark.parametrize("state,geometry,matches", [("ambiguous", "boundary", ["fictional_radio_a"]),
    ("ambiguous", "multiple_matches", ["fictional_radio_a", "fictional_radio_b"]),
    ("unassigned", "missing_coordinates", [])])
def test_ambiguous_and_unassigned_radios_remain_unassigned(state, geometry, matches):
    row = record(assignment_state=state, geometry_status=geometry, matching_radios=matches, radio_candidate=None)
    checks = validate(row)
    assert has(checks, "spatial.consistency", "valido")
    assert has(checks, "spatial.uncertainty", "pendiente_acreditacion")
    assert row["radio_candidate"] is None
    assert has(validate({**row, "radio_candidate": "fictional_radio_a"}), "spatial.consistency", "invalido")


def test_spatial_uncertainty_cannot_disappear_by_changing_state():
    assert has(validate(record(assignment_state="unique_geometry")), "spatial.consistency", "invalido")
    assert has(validate(record(uncertainty_reasons=None)), "spatial.structure", "invalido")


def test_empty_week_without_coverage_stays_unknown():
    row = week()
    before = deepcopy(row)
    checks = validate_week(row)
    assert has(checks, "coverage.unknown", "pendiente_acreditacion")
    assert has(checks, "coverage.consistency", "valido")
    assert row == before and row["casos_observados"] is None
    assert has(validate_week({**row, "casos_observados": 0}), "coverage.consistency", "invalido")


@pytest.mark.parametrize("row,control,status", [(week(raw=1), "coverage.positive", "advertencia"),
    (week(declared="complete", scenario="exploratory"), "coverage.declared_zero", "advertencia"),
    (week(verified="complete"), "coverage.accreditation", "pendiente_acreditacion"),
    (week(verified="complete", pending=1), "coverage.unknown", "pendiente_acreditacion"),
    (week(verified="complete", partial=True), "coverage.unknown", "pendiente_acreditacion")])
def test_existing_coverage_decision_contract_is_preserved(row, control, status):
    checks = validate_week(row)
    assert has(checks, "coverage.consistency", "valido")
    assert has(checks, control, status)


@pytest.mark.parametrize("changes", [{"verificacion_cobertura_ref": None}, {"registros_pendientes_posibles": -1},
    {"registros_elegibles_provisionales": None}, {"ventana_semanal_parcial": None},
    {"version_cobertura": None}, {"zero_policy": None}, {"cobertura_comprobada": "invented"}])
def test_coverage_provenance_and_structure_cannot_be_lost(changes):
    assert any(check.status == "invalido" for check in validate_week(week(verified="complete", **changes)))


def test_experimental_negative_preserves_unknown_original_count_and_status():
    row = label()
    before = deepcopy(row)
    assert has(validate_label(row), "label.experimental", "advertencia")
    assert has(validate_label(row), "label.authorization", "pendiente_acreditacion")
    assert row == before


@pytest.mark.parametrize("changes", [{"autorizacion_cobertura_ref": None}, {"pendientes_semana_objetivo": 1},
    {"semana_objetivo_parcial": True}, {"conteo_original_semana_objetivo": 0},
    {"objetivo_original": 0}, {"cobertura_asumida_no_verificada": False}, {"en_intervalo_autorizado": False},
    {"tipo_etiqueta": "desconocida"}, {"objetivo_valido": False}])
def test_experimental_or_unknown_labels_cannot_be_promoted(changes):
    assert any(check.status == "invalido" for check in validate_label(label(**changes)))


def test_unknown_label_is_null_and_positive_is_provisional():
    assert has(validate_label({"tipo_etiqueta": "desconocida", "objetivo_semana_siguiente": None, "objetivo_valido": False}),
               "label.unknown", "pendiente_acreditacion")
    assert has(validate_label({"tipo_etiqueta": "positivo_provisional", "objetivo_semana_siguiente": 1, "objetivo_valido": True}),
               "label.positive", "advertencia")


def test_correctly_structured_record_is_compatible_but_not_epidemiologically_accredited():
    row = record()
    before = deepcopy(row)
    checks = validate(row)
    assert not any(check.status == "invalido" for check in checks)
    assert has(checks, "record.key", "valido")
    assert has(checks, "date.week", "valido")
    assert has(checks, "spatial.accreditation", "pendiente_acreditacion")
    assert all(check.control_id and check.reason and check.field for check in checks)
    assert row == before
    assert checks == validate(row)


@pytest.mark.parametrize("payload,code", [({"records": []}, 0), ({"records": [{}]}, 1),
    ({"path": "fictional-private-file"}, 2), ({"records": "fictional"}, 2)])
def test_standalone_cli_only_consumes_stdin_and_never_echoes_sensitive_values(monkeypatch, payload, code):
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)
    assert main() == code
    assert "fictional-private-file" not in stdout.getvalue() + stderr.getvalue()
    if code != 2:
        output = json.loads(stdout.getvalue())
        assert output["training_authorized"] is False


def test_no_file_access_or_training_in_validator(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("El validador intentó leer/escribir archivos o entrenar")

    row, cell, target = record(), week(), label()
    monkeypatch.setattr("sklearn.ensemble.RandomForestClassifier.fit", forbidden)
    monkeypatch.setattr("sklearn.ensemble.RandomForestRegressor.fit", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    validate_records([row])
    validate_week(cell)
    validate_label(target)


@pytest.mark.parametrize("changes,control", [({"symptom_onset_status": "missing"}, "date.source_status"),
    ({"fecha_referencia": "2024-01-03"}, "date.reference_alias"),
    ({"crs_confirmed": False}, "spatial.reason")])
def test_existing_traceability_metadata_cannot_contradict_values(changes, control):
    assert has(validate(record(**changes)), control, "invalido")


def test_dossier_addendum_classifies_existing_rules_without_approving_them():
    from sigard_ml.official.epidemiology_review_pipeline import rule_status_addendum

    section = rule_status_addendum()
    assert "Justificadas para comprobación automática" in section
    assert "Experimentales" in section and "Pendientes de evidencia" in section
    assert all(f"P{number}:" in section for number in range(1, 7))
    assert "nunca aprobación sanitaria" in section


def test_declared_episode_resolution_is_not_accredited_by_metadata_alone():
    row = record(identity_resolved_by_review=True, identity_evidence_ref="fictional-review",
                 episode_ref="fictional-reviewed-episode", episode_status="resolved_by_review")
    assert has(validate(row), "episode.resolution", "pendiente_acreditacion")
    assert has(validate({**row, "identity_countable": False}), "episode.resolution", "invalido")
