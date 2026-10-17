"""Fase 4.2: todas las coberturas, filas, ubicaciones y pruebas de respaldo son ficticias."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import json

import pandas as pd
import pytest

from sigard_ml.official.access import AccessDenied, SourceRegistry
from sigard_ml.official.calendar import weeks_between
from sigard_ml.official.coverage_diagnostics import chronological_masks, temporal_inventory
from sigard_ml.official.coverage_panel import build_coverage_panel, validate_coverage_panel
from sigard_ml.official.coverage_pipeline import private_directories, run_coverage_pipeline
from sigard_ml.official.coverage_policy import coverage_map, decide_observation
from sigard_ml.official.coverage_settings import COVERAGE_DEFAULTS, VERIFIED_RULES
from sigard_ml.official.date_recovery_pipeline import run_date_recovery
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.weekly_targets import attach_next_week_target, origin_count_predictors

from test_official_observed import fixture_frame, options, panel_for, prepared, radios
from test_official_date_recovery import recovery_delivery
from test_official_spatial import fictional_delivery


def coverage_options(**changes):
    return {**deepcopy(COVERAGE_DEFAULTS), **changes}


def declaration(state="complete", **changes):
    return {"start": "2024-01-07", "end": "2024-01-27", "state": state,
            "date_panels": ["strict", "expanded"], "declaration_ref": "fictional_statement", **changes}


def verification(root, **changes):
    file = root / "data/interim/official/fictional_verification.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('{"verification":"fictional_only"}', encoding="utf-8")
    return {"start": "2024-01-07", "end": "2024-01-27", "state": "complete",
        "date_panels": ["strict", "expanded"], "verification_ref": "fictional_review",
        "geographic_basis": "patient_residence", "rules_verified": dict.fromkeys(VERIFIED_RULES, True),
        "evidence_files": [{"path": str(file.relative_to(root)), "sha256": digest_path(file)}], **changes}


def coverage_for(frame, radios, settings=None, *, scenario="exploratory", start="2024-01-07", end="2024-01-27", root=None):
    observed_options = options(period_start=start, period_end=end)
    records, _ = prepared(frame, radios, settings=observed_options)
    base = panel_for(records, radios, settings=observed_options)
    result = build_coverage_panel(base, records, settings or coverage_options(), date_panel="strict", scenario=scenario,
        period_start=date.fromisoformat(start), period_end=date.fromisoformat(end), repo_root=root)
    return result, base, records


@pytest.mark.parametrize("declared, verified, scenario, expected", [
    ("complete", "unknown", "conservative", None), ("complete", "unknown", "exploratory", 0),
    ("unknown", "complete", "conservative", 0), ("complete", "complete", "conservative", 0),
    ("partial", "complete", "conservative", None), ("unknown", "partial", "exploratory", None),
    ("unknown", "unknown", "exploratory", None), ("partial", "unknown", "exploratory", None),
])
def test_complete_partial_unknown_and_separation_of_coverage_evidence(declared, verified, scenario, expected):
    count, _, state, provisional = decide_observation(0, 0, declared, verified, scenario)
    assert count == expected
    if expected == 0:
        assert state.startswith("cero_")
        assert provisional == (verified != "complete")


@pytest.mark.parametrize("pending, partial", [(1, False), (0, True), (10, True)])
def test_pending_and_partial_weeks_block_any_zero(pending, partial):
    assert decide_observation(0, pending, "complete", "complete", "conservative", partial_window=partial)[0] is None
    assert decide_observation(0, pending, "complete", "complete", "exploratory", partial_window=partial)[0] is None


def test_positive_counts_are_known_even_if_full_coverage_is_unknown():
    assert decide_observation(2, 3, "unknown", "unknown", "conservative")[0] == 2


@pytest.mark.parametrize("policy", [{"enabled": False, "allow_declared_complete_in_exploratory": True},
                                     {"enabled": True, "allow_declared_complete_in_exploratory": False}])
def test_configurable_zero_policy_can_disable_declared_zeros(policy):
    assert decide_observation(0, 0, "complete", "unknown", "exploratory", zero_policy=policy)[0] is None


def test_midweek_declaration_does_not_fill_boundary_week():
    weeks = weeks_between(date(2024, 1, 7), date(2024, 1, 27))
    mapping = coverage_map([declaration(start="2024-01-10", end="2024-01-23")], ["fictional_radio"], weeks, "strict")
    assert mapping["fictional_radio", date(2024, 1, 7)][0] == "partial"
    assert mapping["fictional_radio", date(2024, 1, 14)][0] == "complete"
    assert mapping["fictional_radio", date(2024, 1, 21)][0] == "partial"


def test_overlapping_intervals_and_unknown_radios_are_rejected():
    weeks = weeks_between(date(2024, 1, 7), date(2024, 1, 27))
    with pytest.raises(ValueError, match="superpuestos"):
        coverage_map([declaration(), declaration()], ["fictional_radio"], weeks, "strict")
    with pytest.raises(ValueError):
        coverage_map([declaration(radio_ids=["alien_radio"])], ["fictional_radio"], weeks, "strict")


def test_verified_coverage_requires_documented_rules_and_intact_private_evidence(tmp_path):
    weeks = weeks_between(date(2024, 1, 7), date(2024, 1, 27))
    entry = verification(tmp_path)
    assert coverage_map([entry], ["fixture"], weeks, "strict", verified=True, repo_root=tmp_path)["fixture", date(2024, 1, 7)][0] == "complete"
    for replacement in ({"rules_verified": {}}, {"evidence_files": []}, {"geographic_basis": "notifying_establishment"},
                        {"verification_ref": None}):
        with pytest.raises(ValueError):
            coverage_map([{**entry, **replacement}], ["fixture"], weeks, "strict", verified=True, repo_root=tmp_path)
    file = tmp_path / entry["evidence_files"][0]["path"]
    file.write_bytes(b"fictional_tampering")
    with pytest.raises(ValueError, match="huella"):
        coverage_map([entry], ["fixture"], weeks, "strict", verified=True, repo_root=tmp_path)


def test_declared_zeros_are_provisional_and_conservative_keeps_them_unknown(radios):
    settings = coverage_options(coverage_declarations=[declaration()])
    exploratory, _, _ = coverage_for(fixture_frame(), radios, settings)
    conservative, _, _ = coverage_for(fixture_frame(), radios, settings, scenario="conservative")
    assert exploratory.casos_observados.eq(0).sum() == 5
    assert exploratory.cero_provisional.sum() == 5
    assert conservative.casos_observados.isna().sum() == 5
    assert not conservative.casos_observados.eq(0).any()
    assert exploratory.objetivo_semana_siguiente.dropna().eq(0).all()
    assert not conservative.objetivo_valido.any()


def test_verified_zeros_and_unknown_coverage_keep_provisional_record_counts(radios, tmp_path):
    settings = coverage_options(coverage_verifications=[verification(tmp_path)])
    panel, _, _ = coverage_for(fixture_frame(), radios, settings, scenario="conservative", root=tmp_path)
    assert panel.casos_observados.eq(0).sum() == 5
    assert not panel.cero_provisional.any()
    assert not panel.apto_entrenamiento.any()
    assert panel.objetivo_provisional[panel.objetivo_valido].all()


def test_undated_pending_blocks_all_possible_weeks_only_for_candidate_radio(radios):
    frame = fixture_frame(2)
    frame.loc[1, ["symptom_onset", "symptom_onset_status"]] = [None, "missing"]
    panel, _, _ = coverage_for(frame, radios, coverage_options(coverage_declarations=[declaration()]))
    affected = panel[panel.radio_censal.eq("460140001")]
    assert affected.registros_pendientes_posibles.eq(1).all()
    assert affected.casos_observados.isna().sum() == 2 and not affected.casos_observados.eq(0).any()
    unaffected = panel[panel.radio_censal.eq("460140101")]
    assert unaffected.casos_observados.eq(0).all()


def test_uncertain_identity_blocks_zero_in_known_week_without_deleting_rows(radios):
    frame = fixture_frame(2)
    frame.loc[1, "event_ref"] = frame.loc[0, "event_ref"]
    panel, _, records = coverage_for(frame, radios, coverage_options(coverage_declarations=[declaration()]))
    assert len(records) == 2 and records.processing_outcome.eq("pending").all()
    first_week = panel[panel.fecha_inicio_semana.eq(date(2024, 1, 7)) & panel.radio_censal.eq("460140001")]
    assert first_week.casos_observados.isna().all() and first_week.registros_pendientes_posibles.eq(2).all()
    assert panel.casos_observados.eq(0).sum() == 5


def test_undated_unknown_radio_blocks_zeros_over_entire_grid(radios):
    frame = fixture_frame()
    frame.loc[0, ["symptom_onset", "symptom_onset_status", "radio_candidate"]] = [None, "missing", None]
    panel, _, _ = coverage_for(frame, radios, coverage_options(coverage_declarations=[declaration()]))
    assert panel.casos_observados.isna().all()


def test_valid_and_invalid_zeros_are_checked(radios):
    panel, _, _ = coverage_for(fixture_frame(), radios)
    changed = panel.copy()
    index = changed.casos_observados.isna().idxmax()
    changed.loc[index, "casos_observados"] = 0
    with pytest.raises(ValueError, match="Cero"):
        validate_coverage_panel(changed)


def target_fixture(starts, counts):
    return pd.DataFrame({"radio_censal": ["fictional_radio"] * len(starts),
        "anio_epidemiologico": [2024] * len(starts), "semana_epidemiologica": list(range(1, len(starts) + 1)),
        "fecha_inicio_semana": starts, "fecha_fin_semana": [day + timedelta(days=6) for day in starts],
        "casos_observados": pd.array(counts, dtype="Int64"),
        "estado_observacion": ["cero_declarado_provisional" if count == 0 else "positivo_provisional" for count in counts],
        "cero_provisional": [count == 0 for count in counts], "registros_fecha_aproximada": [0] * len(starts)})


def test_targets_are_1_0_and_null_and_last_week_has_no_target():
    start = date(2024, 1, 7)
    panel = attach_next_week_target(target_fixture([start + timedelta(days=7 * i) for i in range(4)], [None, 3, 0, None]))
    assert panel.objetivo_semana_siguiente.iloc[:2].tolist() == [1, 0]
    assert panel.objetivo_semana_siguiente.iloc[2:].isna().all()
    assert panel.objetivo_valido.tolist() == [True, True, False, False]


def test_missing_week_does_not_jump_to_next_observed_week():
    panel = attach_next_week_target(target_fixture([date(2024, 1, 7), date(2024, 1, 21)], [1, 1]))
    assert panel.objetivo_semana_siguiente.isna().all()


def test_next_week_target_crosses_epidemiological_year_without_iso_shift(radios):
    frame = fixture_frame()
    frame.loc[0, "symptom_onset"] = date(2024, 1, 2)
    panel, _, _ = coverage_for(frame, radios, start="2023-12-24", end="2024-01-06")
    origin = panel[panel.fecha_inicio_semana.eq(date(2023, 12, 24)) & panel.radio_censal.eq("460140001")].iloc[0]
    assert (origin.anio_epidemiologico, origin.semana_epidemiologica) == (2023, 52)
    assert origin.objetivo_semana_siguiente == 1 and origin.fecha_inicio_semana_objetivo == date(2023, 12, 31)


def test_target_lookahead_is_not_exported_as_origin_predictor():
    starts = [date(2024, 1, 7), date(2024, 1, 14)]
    first = attach_next_week_target(target_fixture(starts, [2, 3]))
    changed = attach_next_week_target(target_fixture(starts, [2, 0]))
    pd.testing.assert_series_equal(origin_count_predictors(first).iloc[0], origin_count_predictors(changed).iloc[0])
    assert first.objetivo_semana_siguiente.iloc[0] == 1 and changed.objetivo_semana_siguiente.iloc[0] == 0
    assert "objetivo_semana_siguiente" not in origin_count_predictors(first)
    assert "fecha_inicio_semana_objetivo" not in origin_count_predictors(first)


def test_chronological_split_excludes_target_crossing_evaluation_boundary():
    starts = [date(2023, 12, 24), date(2023, 12, 31), date(2024, 1, 7), date(2024, 1, 14)]
    panel = attach_next_week_target(target_fixture(starts, [2, 3, 4, 5]))
    train, evaluation = chronological_masks(panel, date(2024, 1, 7))
    assert train.tolist() == [True, False, False, False]
    assert evaluation.tolist() == [False, False, True, False]


def test_reproducible_coverage_preserves_prior_panel_and_audit(radios):
    panel, base, records = coverage_for(fixture_frame(), radios, coverage_options(coverage_declarations=[declaration()]))
    before_base, before_records = base.copy(deep=True), records.copy(deep=True)
    repeated = build_coverage_panel(base, records, coverage_options(coverage_declarations=[declaration()]), date_panel="strict",
        scenario="exploratory", period_start=date(2024, 1, 7), period_end=date(2024, 1, 27))
    pd.testing.assert_frame_equal(panel, repeated)
    pd.testing.assert_frame_equal(base, before_base)
    pd.testing.assert_frame_equal(records, before_records)


@pytest.fixture
def coverage_delivery(recovery_delivery, monkeypatch):
    root, config, registry, source = recovery_delivery
    run_date_recovery(config, registry, root, baseline_dir="data/interim/official/observed/exploratory")
    monkeypatch.setattr("sigard_ml.official.coverage_pipeline.require_branch", lambda root: None)
    return root, config, registry, source


def test_complete_private_pipeline_separates_scenarios_and_preserves_prior_phases(coverage_delivery):
    root, config, registry, _ = coverage_delivery
    settings = coverage_options(coverage_declarations=[declaration()])
    output = root / settings["output_dir"]
    before = protected_snapshot(root, output)
    report = run_coverage_pipeline(config, registry, settings, root)
    hashes = {str(path.relative_to(output)): digest_path(path) for path in output.rglob("*") if path.is_file()}
    repeated = run_coverage_pipeline(config, registry, settings, root)
    assert report == repeated
    assert hashes == {str(path.relative_to(output)): digest_path(path) for path in output.rglob("*") if path.is_file()}
    require_preserved(before, protected_snapshot(root, output))
    assert report["panels"]["expanded"]["exploratory"]["observations"]["negative"] > 0
    assert report["panels"]["expanded"]["conservative"]["observations"]["negative"] == 0
    assert report["panels"]["strict"]["exploratory"]["observations"]["positive"] == 0
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert not metadata["training_ready"] and not metadata["validated_epidemiological_absence"]
    assert metadata["location_role_from_previous_phase"] == "unknown"
    assert "FICTIONAL_PRIVATE_PERSON" not in (output / "viability.md").read_text(encoding="utf-8")


def test_coverage_output_cannot_overwrite_previous_phase_or_public_data(tmp_path):
    for path in (COVERAGE_DEFAULTS["input_dir"], "data/interim/official/observed", "data/processed/official",
                 "frontend/public/data", "../outside"):
        with pytest.raises(ValueError):
            private_directories(coverage_options(output_dir=path), tmp_path)


def test_coverage_requires_authorization_before_reading_private_inputs(coverage_delivery, monkeypatch):
    root, config, registry, _ = coverage_delivery
    monkeypatch.setattr("sigard_ml.official.coverage_pipeline.protected_snapshot", lambda *args: pytest.fail("No leer sin autorización"))
    denied = SourceRegistry((replace(registry.sources[0], enabled=False),))
    with pytest.raises(AccessDenied):
        run_coverage_pipeline(config, denied, coverage_options(), root)


def test_manifest_tampering_stops_before_new_outputs(coverage_delivery):
    root, config, registry, _ = coverage_delivery
    original = root / "data/interim/official/observed/date_recovery_041/expanded/exploratory/panel.parquet"
    original.write_bytes(original.read_bytes() + b"fictional_corruption")
    with pytest.raises(ValueError, match="manifiesto"):
        run_coverage_pipeline(config, registry, coverage_options(), root)
    assert not (root / COVERAGE_DEFAULTS["output_dir"]).exists()


def test_source_names_and_positive_intervals_do_not_prove_coverage():
    normalized = pd.DataFrame({"source_id": ["delivery_2099", "delivery_2099"],
        "symptom_onset": [date(2023, 12, 31), date(2024, 1, 14)], "symptom_onset_status": ["valid"] * 2,
        "sample_on": [None, None], "sample_on_status": ["missing"] * 2})
    records = pd.DataFrame({"source_id": ["delivery_2099"] * 2, "processing_outcome": ["included"] * 2,
        "classification": ["confirmado"] * 2,
        "reference_date": normalized.symptom_onset, "week_start": [date(2023, 12, 31), date(2024, 1, 14)],
        "tipo_fecha_referencia": ["inicio_sintomas"] * 2, "radio_candidate": ["fixture"] * 2})
    result = temporal_inventory(normalized, {"strict": records}, date(2023, 12, 31), date(2024, 1, 20), [])
    source = result["sources"][0]
    assert not source["requested_period_documented"] and not source["coverage_complete_proven"]
    assert source["observed_date_intervals"]["symptom_onset"]["observed_start"] == "2023-12-31"
    assert result["date_panels"]["strict"]["weeks_without_included_records"] == ["2024-01-07"]


def test_declared_period_for_expanded_dates_does_not_silently_cover_strict_dates():
    weeks = weeks_between(date(2024, 1, 7), date(2024, 1, 27))
    entry = declaration(date_panels=["expanded"])
    assert not coverage_map([entry], ["fictional_radio"], weeks, "strict")
    assert len(coverage_map([entry], ["fictional_radio"], weeks, "expanded")) == 3


def test_approximate_target_date_is_preserved_without_changing_reference_week():
    panel = target_fixture([date(2024, 1, 7), date(2024, 1, 14)], [None, 1])
    panel.loc[1, "registros_fecha_aproximada"] = 1
    result = attach_next_week_target(panel)
    assert result.objetivo_con_fecha_aproximada.tolist() == [True, False]
    assert result.fecha_inicio_semana_objetivo.iloc[0] == date(2024, 1, 14)
