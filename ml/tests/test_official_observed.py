"""Fase 4: todas las filas, IDs, fechas, libros y posiciones son ficticios."""

from datetime import date, timedelta
import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from sigard_ml.official.calendar import make_week, week_from_date, weeks_between
from sigard_ml.official.classification import classify_labels, prepare_classification_map
from sigard_ml.official.coverage import observation_state
from sigard_ml.official.eligibility import evaluate_eligibility
from sigard_ml.official.episodes import event_reference, review_episode_groups
from sigard_ml.official.observed_auxiliary import attach_auxiliary_values
from sigard_ml.official.observed_dates import assign_record_weeks
from sigard_ml.official.observed_panel import build_observed_panel, validate_observed_panel
from sigard_ml.official.observed_pipeline import (
    observed_output, prepare_records, private_record_projection, run_observed_pipeline,
)
from sigard_ml.official.observed_reports import reconciliation
from sigard_ml.official.observed_settings import OBSERVED_DEFAULTS, ROW_KEY
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved, run_spatial_diagnostics
from sigard_ml.official.spatial_settings import SPATIAL_DEFAULTS

# Reutiliza la entrega mínima de Fase 3: no accede a la entrega real del proyecto.
from test_official_spatial import fictional_delivery


@pytest.fixture
def radios():
    return gpd.GeoDataFrame({"radio_id": ["460140001", "460140101"]},
                           geometry=[box(-67, -30, -66.999, -29.999),
                                     box(-66.999, -30, -66.998, -29.999)], crs=4326)


def fixture_frame(size=1):
    return pd.DataFrame({"source_id": ["fixture"] * size, "sheet_ref": ["sheet_01"] * size,
        "record_ref": [f"fictional_record_{i}" for i in range(size)],
        "event_ref": [event_reference(f"fictional_event_{i}") for i in range(size)],
        "classification_label": ["CASO CONFIRMADO"] * size,
        "symptom_onset": [date(2024, 1, 10)] * size, "symptom_onset_status": ["valid"] * size,
        "radio_candidate": ["460140001"] * size, "assignment_state": ["uncertain"] * size,
        "geometry_status": ["unique_interior"] * size, "geocoding_category": ["street_word"] * size,
        "uncertainty_reasons": [["positional_accuracy_undocumented"] for _ in range(size)],
        "distance_to_boundary_m": [10.0] * size, "alternative_radios": [[] for _ in range(size)],
        "alternative_basis": [None] * size, "coordinate_group_ref": ["fictional_coordinate"] * size,
        "coordinate_group_size": [size] * size, "crs_confirmed": [False] * size, "location_role": ["unknown"] * size})


def options(**changes):
    return {**OBSERVED_DEFAULTS, "period_start": "2024-01-07", "period_end": "2024-01-20",
            "spatial_version": "fictional_spatial_v1", **changes}


def prepared(frame, radios, *, exploratory=True, settings=None):
    return prepare_records(frame, radios, {"as_of_date": "2024-12-31"}, settings or options(), exploratory)


def panel_for(frame, radios, *, settings=None, exploratory=True):
    settings = settings or options()
    return build_observed_panel(frame, radios, period_start=date.fromisoformat(settings["period_start"]),
                               period_end=date.fromisoformat(settings["period_end"]), options=settings,
                               exploratory=exploratory, expected_count=2)


def test_classification_uses_exact_field_values_not_embedded_words():
    labels = ["  CASO   CONFIRMADO  ", "Caso confirmado DEN-1", "historia larga: caso confirmado",
              "No confirmado", "Caso confirmado DEN-99", None, "Caso sospechoso", "Caso probable", "Descartado"]
    result = classify_labels(labels, OBSERVED_DEFAULTS["classification_map"], "fictional_v1")
    assert result.classification.tolist() == ["confirmado", "confirmado", "indeterminado", "indeterminado",
                                             "indeterminado", "indeterminado", "sospechoso", "probable", "descartado"]
    with pytest.raises(ValueError):
        prepare_classification_map({"Confirmado": "confirmado", "CONFIRMADO": "descartado"})


def test_conservative_and_explicit_exploratory_eligibility_are_separate():
    categories = ["confirmado", "probable", "sospechoso", "descartado", "indeterminado"]
    rule = dict(include=["confirmado"], exclude=["probable", "sospechoso", "descartado"], version="fixture")
    conservative = evaluate_eligibility(categories, **rule)
    exploratory = evaluate_eligibility(categories, exploratory=True, **rule)
    assert conservative.analysis_eligibility.tolist() == ["review", "review", "review", "excluded", "review"]
    assert exploratory.analysis_eligibility.tolist() == ["eligible_provisional", "excluded", "excluded", "excluded", "review"]
    assert not exploratory.epidemiological_eligibility_validated.any()
    with pytest.raises(ValueError):
        evaluate_eligibility(categories, exploratory=True, include=["indeterminado"], version="fixture")


def test_ids_are_opaque_repeated_groups_pending_and_rows_preserved():
    frame = fixture_frame(3)
    frame.loc[1, "event_ref"] = frame.loc[0, "event_ref"]
    frame.loc[2, "event_ref"] = None
    before = frame.copy(deep=True)
    result = review_episode_groups(frame, version="fixture")
    assert result.episode_status.tolist() == ["repeated_identifier_pending", "repeated_identifier_pending", "missing_identifier_pending"]
    assert not result.identity_countable.any() and len(result) == 3
    assert event_reference(123) == event_reference("123")
    assert event_reference("fictional_event") != "fictional_event"
    pd.testing.assert_frame_equal(frame, before)


def test_manual_episode_resolution_never_picks_first_automatically():
    frame = fixture_frame(2)
    frame.loc[1, "event_ref"] = frame.loc[0, "event_ref"]
    resolutions = [{"record_key": row[ROW_KEY].tolist(), "episode_ref": "fictional_episode",
                    "countable": index == 1, "evidence_ref": "fictional_review"} for index, row in frame.iterrows()]
    result = review_episode_groups(frame, version="fixture", resolutions=resolutions)
    assert result.identity_countable.tolist() == [False, True]
    assert result.identity_resolved_by_review.all()
    assert result.episode_status.tolist() == ["resolved_nonrepresentative", "resolved_by_review"]
    with pytest.raises(ValueError, match="todo el grupo"):
        review_episode_groups(frame, version="fixture", resolutions=resolutions[:1])
    with pytest.raises(ValueError, match="exactamente un"):
        review_episode_groups(frame, version="fixture", resolutions=[{**r, "countable": True} for r in resolutions])


def test_reused_identifier_can_represent_distinct_reviewed_episodes_without_time_or_address_matching():
    frame = fixture_frame(2)
    frame.loc[1, "event_ref"] = frame.loc[0, "event_ref"]
    frame["symptom_onset"] = [date(2020, 1, 10), date(2024, 1, 10)]
    before = frame.copy(deep=True)
    pending = review_episode_groups(frame, version="fictional_reuse_v1")
    assert len(pending) == 2 and not pending.identity_countable.any()
    # Sólo una resolución documentada puede decidir que son episodios distintos;
    # ni el tiempo transcurrido ni la coordenada compartida deciden identidad.
    resolutions = [{"record_key": row[ROW_KEY].tolist(), "episode_ref": f"fictional_episode_{index}",
                    "countable": True, "evidence_ref": "fictional_review"} for index, row in frame.iterrows()]
    reviewed = review_episode_groups(frame, version="fictional_reuse_v1", resolutions=resolutions)
    assert reviewed.identity_countable.all() and reviewed.episode_ref.nunique() == 2
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("day, year, number, start", [
    (date(2020, 1, 1), 2020, 1, date(2019, 12, 29)),
    (date(2020, 12, 27), 2020, 53, date(2020, 12, 27)),
    (date(2021, 1, 2), 2020, 53, date(2020, 12, 27)),
    (date(2021, 1, 3), 2021, 1, date(2021, 1, 3)),
    (date(2023, 12, 30), 2023, 52, date(2023, 12, 24)),
    (date(2023, 12, 31), 2024, 1, date(2023, 12, 31)),
    (date(2024, 12, 29), 2025, 1, date(2024, 12, 29)),
])
def test_date_to_week_preserves_sunday_saturday_year_transitions(day, year, number, start):
    week = week_from_date(day)
    assert (week.year, week.number, week.start) == (year, number, start)
    assert week.end == start + timedelta(days=6)
    assert make_week(year, number) == week


def test_missing_invalid_future_and_outside_dates_never_use_sample_as_fallback():
    frame = fixture_frame(4)
    frame["symptom_onset"] = [None, None, date(2024, 12, 31), date(2023, 1, 1)]
    frame["symptom_onset_status"] = ["missing", "invalid_format", "valid", "valid"]
    frame["sample_on"] = [date(2024, 1, 10)] * 4
    frame["sample_on_status"] = ["valid"] * 4
    rule = dict(period_start=date(2024, 1, 7), period_end=date(2024, 1, 20), as_of=date(2024, 6, 1), version="fixture")
    result = assign_record_weeks(frame, field="symptom_onset", **rule)
    assert result.reference_date_status.tolist() == ["missing", "invalid_format", "future_date", "outside_analysis_period"]
    assert result.week_start.isna().all()
    alternative = assign_record_weeks(frame, field="sample_on", **rule)
    assert alternative.date_within_analysis_period.all()


def test_provisional_counts_keep_empty_cells_null_and_identity_unvalidated(radios):
    records, conservative = prepared(fixture_frame(), radios)
    panel = panel_for(records, radios)
    assert len(panel) == 4
    assert panel.registros_elegibles_provisionales.dropna().tolist() == [1]
    assert panel.registros_elegibles_provisionales.isna().sum() == 3
    assert not panel.validado.any() and not panel.apto_entrenamiento.any()
    assert panel.radio_censal.map(type).eq(str).all()
    assert set(panel.fraccion_censal) == {"4601400", "4601401"}
    report = reconciliation(records, panel, conservative)
    assert report["reconciliation_verified"] and report["explicit_zero_cells"] == 0


def test_default_conservative_panel_does_not_count_confirmed_labels(radios):
    records, _ = prepared(fixture_frame(), radios, exploratory=False)
    panel = panel_for(records, radios, exploratory=False)
    assert panel.registros_elegibles_provisionales.isna().all()
    assert records.processing_outcome.tolist() == ["pending"]


def test_repeated_ids_excluded_from_main_count_and_reconcile_without_row_deletion(radios):
    frame = fixture_frame(3)
    frame.loc[1, "event_ref"] = frame.loc[0, "event_ref"]
    records, conservative = prepared(frame, radios)
    assert records.processing_outcome.tolist() == ["pending", "pending", "included"]
    panel = panel_for(records, radios)
    assert int(panel.registros_elegibles_provisionales.sum()) == 1
    assert panel.registros_pendientes_posibles.max() == 2
    assert reconciliation(records, panel, conservative)["reconciliation_verified"]
    assert len(records) == 3


def test_positive_and_negative_evidence_rules_do_not_fabricate_training_negatives():
    assert observation_state(0, 0, "unknown") == (None, "sin_informacion_suficiente", "unknown")
    assert observation_state(0, 0, "complete") == (0, "cero_con_cobertura_comprobada", "complete")
    assert observation_state(0, 1, "complete") == (None, "cobertura_parcial", "partial")
    assert observation_state(0, 0, "partial") == (None, "cobertura_parcial", "partial")
    assert observation_state(0, 0, "outside") == (None, "fuera_de_cobertura", "outside")
    assert observation_state(0, 0, "complete", partial_window=True) == (None, "cobertura_parcial", "partial")
    with pytest.raises(ValueError):
        observation_state(1, 0, "outside")


def test_complete_coverage_needs_evidence_and_unresolved_date_blocks_zeros(radios):
    settings = options(coverage=[{"start": "2024-01-07", "end": "2024-01-20", "state": "complete", "evidence_ref": "fictional_coverage"}])
    frame = fixture_frame(2)
    frame.loc[1, ["symptom_onset", "symptom_onset_status"]] = [None, "missing"]
    records, _ = prepared(frame, radios, settings=settings)
    panel = panel_for(records, radios, settings=settings)
    first = panel[panel.radio_censal.eq("460140001")]
    second = panel[panel.radio_censal.eq("460140101")]
    assert first.estado_observacion.eq("cobertura_parcial").all()
    assert first.registros_elegibles_provisionales.isna().sum() == 1
    assert second.registros_elegibles_provisionales.eq(0).all()
    with pytest.raises(ValueError):
        panel_for(records, radios, settings=options(coverage=[{"start": "2024-01-07", "end": "2024-01-20", "state": "complete"}]))


def test_unknown_radio_pending_prevents_zero_in_all_possible_radios(radios):
    settings = options(coverage=[{"start": "2024-01-07", "end": "2024-01-20", "state": "complete", "evidence_ref": "fixture"}])
    frame = fixture_frame()
    frame.loc[0, "radio_candidate"] = None
    records, _ = prepared(frame, radios, settings=settings)
    panel = panel_for(records, radios, settings=settings)
    affected = panel[panel.fecha_inicio_semana.eq(date(2024, 1, 7))]
    assert affected.estado_observacion.eq("cobertura_parcial").all()
    assert affected.registros_elegibles_provisionales.isna().all()


def test_duplicate_technical_keys_are_rejected(radios):
    frame = fixture_frame(2)
    frame.loc[1, ROW_KEY] = frame.loc[0, ROW_KEY].tolist()
    with pytest.raises(ValueError):
        prepared(frame, radios)


def test_reproducible_panel_and_input_preservation(radios):
    frame = fixture_frame(2)
    before = frame.copy(deep=True)
    records, _ = prepared(frame, radios)
    first = panel_for(records, radios)
    second = panel_for(records, radios.iloc[::-1])
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("name, available, radio", [
    ("target_cases_next_week", date(2024, 1, 13), "460140001"),
    ("population", date(2024, 1, 14), "460140001"),
    ("population", date(2024, 1, 13), "999990001"),
])
def test_auxiliaries_reject_target_future_and_wrong_territory(radios, name, available, radio):
    records, _ = prepared(fixture_frame(), radios)
    panel = panel_for(records, radios)
    auxiliary = pd.DataFrame([{"radio_censal": radio, "fecha_inicio_semana": date(2024, 1, 7),
        "name": name, "value": 100, "observed_through": date(2024, 1, 7), "available_on": available,
        "source_ref": "fictional_source_v1"}])
    with pytest.raises(ValueError):
        attach_auxiliary_values(panel, auxiliary)


def test_auxiliary_valid_join_keeps_nulls_and_private_projection_excludes_persons(radios):
    frame = fixture_frame()
    frame["address"] = "FICTIONAL_PRIVATE_ADDRESS"
    frame["longitude_candidate"] = -66.9995
    records, _ = prepared(frame, radios)
    panel = panel_for(records, radios)
    auxiliary = pd.DataFrame([{"radio_censal": "460140001", "fecha_inicio_semana": date(2024, 1, 7),
        "name": "population", "value": 100, "observed_through": date(2023, 1, 1), "available_on": date(2023, 1, 2),
        "source_ref": "fictional_census_v1"}])
    joined = attach_auxiliary_values(panel, auxiliary)
    assert joined.population.dropna().tolist() == [100]
    assert joined.population_source_ref.dropna().tolist() == ["fictional_census_v1"]
    assert joined.registros_elegibles_provisionales.isna().sum() == 3
    projection = private_record_projection(records)
    assert "address" not in projection and "longitude_candidate" not in projection and "classification_label" not in projection
    assert "FICTIONAL_PRIVATE_ADDRESS" not in projection.to_json()


def test_validator_rejects_changed_week_and_invented_count_on_missing_cell(radios):
    records, _ = prepared(fixture_frame(), radios)
    panel = panel_for(records, radios)
    weeks = weeks_between(date(2024, 1, 7), date(2024, 1, 20))
    changed = panel.copy()
    changed.loc[0, "fecha_inicio_semana"] = date(2025, 1, 5)
    with pytest.raises(ValueError, match="Grilla"):
        validate_observed_panel(changed, radios.radio_id.tolist(), weeks, 1)
    changed = panel.copy()
    empty_index = changed.registros_elegibles_provisionales.isna().idxmax()
    changed.loc[empty_index, "registros_elegibles_provisionales"] = 1
    with pytest.raises(ValueError, match="ausencia"):
        validate_observed_panel(changed, radios.radio_id.tolist(), weeks, 2)


def test_branch_guard_rejects_other_branches_before_private_reads(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from sigard_ml.official.observed_pipeline import require_branch
    monkeypatch.setattr("sigard_ml.official.observed_pipeline.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(stdout="main\n"))
    with pytest.raises(ValueError, match="entrenamiento-ML"):
        require_branch(tmp_path)


def test_private_outputs_reject_public_or_prior_phase_folders(tmp_path):
    for folder in ("data/processed/official", "data/interim/official", "data/interim/official/normalized",
                   "data/interim/official/geography", "frontend/public/data", "../outside"):
        with pytest.raises(ValueError):
            observed_output(options(output_dir=folder), tmp_path, True)


@pytest.fixture
def phase4_delivery(fictional_delivery, monkeypatch):
    root, config, registry, source = fictional_delivery
    run_spatial_diagnostics(config, registry, dict(SPATIAL_DEFAULTS), root)
    monkeypatch.setattr("sigard_ml.official.observed_pipeline.require_branch", lambda root: None)
    return root, config, registry, source


def test_end_to_end_uses_previous_phases_preserves_sources_and_reproduces_outputs(phase4_delivery):
    root, config, registry, _ = phase4_delivery
    settings = dict(OBSERVED_DEFAULTS)
    output = observed_output(settings, root, True)
    before = protected_snapshot(root, output)
    report = run_observed_pipeline(config, registry, settings, root, exploratory=True)
    require_preserved(before, protected_snapshot(root, output))
    panel = pd.read_parquet(output / "panel.parquet")
    audit = pd.read_parquet(output / "records_audit.parquet")
    assert len(audit) == 3 and int(panel.registros_elegibles_provisionales.sum()) == 1
    assert panel.registros_elegibles_provisionales.eq(0).sum() == 0
    assert set(audit.processing_outcome) == {"included", "pending"}
    assert "latitude_candidate" not in audit and "classification_label" not in audit
    assert report["summary"]["reconciliation_verified"]
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["temporal_mode"] == "retrospective" and not metadata["training_ready"]
    assert metadata["provenance"]["spatial_assignment"]["assignment_sha256"]
    hashes = {path.name: digest_path(path) for path in output.iterdir()}
    run_observed_pipeline(config, registry, settings, root, exploratory=True)
    assert hashes == {path.name: digest_path(path) for path in output.iterdir()}
    run_observed_pipeline(config, registry, settings, root)
    conservative = pd.read_parquet(observed_output(settings, root, False) / "panel.parquet")
    assert conservative.registros_elegibles_provisionales.isna().all()
    assert hashes == {path.name: digest_path(path) for path in output.iterdir()}
    conservative_output = observed_output(settings, root, False)
    conservative_hashes = {path.name: digest_path(path) for path in conservative_output.iterdir()}
    run_observed_pipeline(config, registry, settings, root, exploratory=True)
    assert hashes == {path.name: digest_path(path) for path in output.iterdir()}
    run_observed_pipeline(config, registry, settings, root)
    assert conservative_hashes == {path.name: digest_path(path) for path in conservative_output.iterdir()}


def test_tampered_assignment_is_rejected_before_output(phase4_delivery):
    root, config, registry, _ = phase4_delivery
    path = root / "data/interim/official/geography/assignments.parquet"
    path.write_bytes(path.read_bytes() + b"fictional_corruption")
    with pytest.raises(ValueError, match="manifiesto"):
        run_observed_pipeline(config, registry, dict(OBSERVED_DEFAULTS), root, exploratory=True)
    assert not observed_output(OBSERVED_DEFAULTS, root, True).exists()
