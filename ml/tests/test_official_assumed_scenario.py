"""Ficticios: autorización, bloqueos, t+1; integración prohíbe fit y Excel."""

from dataclasses import replace
from datetime import date
import json
import subprocess

import pandas as pd
import pytest

from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.spatial_ml.assumed_scenario import VERSION, ZERO_KIND, validate_authorization, materialize_labels, chronological_review
from sigard_ml.official.spatial_ml.assumed_scenario_pipeline import DEFAULTS, paths, run_scenario, snapshot
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.features import KEYS, build_features
from sigard_ml.official.spatial_ml.pipeline import verify_private_manifest
from sigard_ml.official.spatial_ml.splits import class_counts
from sigard_ml.official.spatial_pipeline import digest_path, require_preserved
from sigard_ml.official.weekly_targets import attach_next_week_target
from test_official_spatial_ml import fixture_panel, static_fixture, NEIGHBORS, RADIOS


def authorization(**changes):
    return {"version": VERSION, "declaration_ref": "fictional_assumption", "responsible_ref": "fictional",
        "decision_ref": "fictional_explicit_instruction", "justification": "fictional_technical_research",
        "start": "2024-01-07", "end": "2024-06-08", "source_ids": ["delivery_2024_2026"],
        "radio_scope": "all_263_capital_radios", "date_policy": "expanded",
        "coverage_kind": "assumed_experimental_not_verified", "materialization_authorized": True,
        "training_authorized": False, "pending_policy": "preserve_all_existing_blockers",
        "ready_universe_records": 7720, "clinical_confirmation_inferred": False, **changes}


def panel_fixture():
    return fixture_panel({radio: [None, 1] * 54 for radio in RADIOS}, start=date(2022, 12, 18), size=108)


@pytest.mark.parametrize("changes", [
    {"materialization_authorized": False}, {"training_authorized": True}, {"coverage_kind": "verified"},
    {"date_policy": "strict"}, {"start": "2024-01-01"}, {"end": "2024-12-31"},
    {"source_ids": ["delivery_2022"]}, {"justification": ""}, {"responsible_ref": ""},
    {"decision_ref": ""}, {"pending_policy": "ignore"}, {"clinical_confirmation_inferred": True},
    {"ready_universe_records": 8000}, {"radio_scope": "any"}, {"unexpected": True},
])
def test_rejects_unauthorized_scope_or_actions(changes):
    with pytest.raises(ValueError):
        validate_authorization(authorization(**changes))


def test_exact_target_bounds_provenance_and_immutable_observed_counts():
    panel = panel_fixture()
    before = panel.copy(deep=True)
    labels, weekly = materialize_labels(panel, authorization())
    pd.testing.assert_frame_equal(panel, before)
    pd.testing.assert_series_equal(weekly.casos_observados, before.casos_observados)
    new = labels.tipo_etiqueta.eq(ZERO_KIND)
    assert new.any() and labels.loc[new, "objetivo_original"].isna().all()
    assert labels.loc[new, "objetivo_semana_siguiente"].eq(0).all()
    assert labels.loc[new, "cobertura_asumida_no_verificada"].all()
    assert labels.loc[new, "objetivo_provisional"].all() and not labels.apto_entrenamiento.any()
    assert labels.loc[new, "fecha_inicio_semana_objetivo"].between(date(2024, 1, 7), date(2024, 6, 2)).all()
    first = labels.fecha_inicio_semana.eq(date(2023, 12, 31))
    assert labels.loc[first, "fecha_inicio_semana_objetivo"].eq(date(2024, 1, 7)).all()
    assert labels.loc[first, "en_intervalo_autorizado"].all()
    outside = ~labels.en_intervalo_autorizado.eq(True)
    pd.testing.assert_series_equal(labels.loc[outside, "objetivo_original"], labels.loc[outside, "objetivo_semana_siguiente"], check_names=False)


def test_pending_partial_and_positive_preserved_at_target_not_origin():
    panel = fixture_panel({radio: [None] * 56 for radio in RADIOS}, size=56)
    mask = panel.radio_censal.eq(RADIOS[0])
    panel.loc[mask & panel.fecha_inicio_semana.eq(date(2024, 1, 7)), "registros_pendientes_posibles"] = 1
    panel.loc[mask & panel.fecha_inicio_semana.eq(date(2024, 1, 14)), "ventana_semanal_parcial"] = True
    pos = mask & panel.fecha_inicio_semana.eq(date(2024, 1, 21))
    panel.loc[pos, "casos_observados"] = 3
    panel.loc[pos, "registros_pendientes_posibles"] = 2
    panel.loc[pos, "registros_fecha_aproximada"] = 1
    labels, _ = materialize_labels(attach_next_week_target(panel), authorization())
    rows = labels[labels.radio_censal.eq(RADIOS[0])].set_index("fecha_inicio_semana_objetivo")
    assert pd.isna(rows.loc[date(2024, 1, 7), "objetivo_semana_siguiente"])
    assert pd.isna(rows.loc[date(2024, 1, 14), "objetivo_semana_siguiente"])
    assert rows.loc[date(2024, 1, 21), "objetivo_semana_siguiente"] == 1
    assert rows.loc[date(2024, 1, 21), "objetivo_con_fecha_aproximada"]
    assert rows.loc[date(2024, 1, 28), "tipo_etiqueta"] == ZERO_KIND


def test_missing_target_week_never_jumps_gap():
    panel = panel_fixture()
    panel = panel[panel.fecha_inicio_semana.ne(date(2024, 1, 7))].reset_index(drop=True)
    labels, _ = materialize_labels(attach_next_week_target(panel), authorization())
    assert labels.loc[labels.fecha_inicio_semana.eq(date(2023, 12, 31)), "objetivo_semana_siguiente"].isna().all()


@pytest.mark.parametrize("field,value", [("registros_pendientes_posibles", None),
    ("registros_pendientes_posibles", -1), ("ventana_semanal_parcial", None), ("panel_fechas", "strict")])
def test_unknown_blockers_and_wrong_policy_rejected(field, value):
    panel = panel_fixture()
    if field == "ventana_semanal_parcial":
        panel[field] = panel[field].astype("object")
    panel.loc[0, field] = value
    with pytest.raises(ValueError):
        materialize_labels(panel, authorization())


def test_supported_zero_not_relabelled_as_assumed():
    panel = fixture_panel({radio: [0] * 56 for radio in RADIOS}, size=56)
    labels, _ = materialize_labels(panel, authorization())
    assert not labels.tipo_etiqueta.eq(ZERO_KIND).any()
    assert labels.tipo_etiqueta.eq("cero_heredado_bajo_politica_origen").sum() == 110


def test_chronological_purge_support_and_scoped_membership():
    labels, _ = materialize_labels(panel_fixture(), authorization())
    parts, reports = chronological_review(labels)
    scoped = next(row for row in reports if row["name"] == "authorized_2024_only")
    assert scoped["both_classes_in_every_partition"] and not scoped["training_authorized"]
    assert [scoped["partitions"][name]["target_weeks"] for name in ("train", "validation", "test")] == [8, 8, 4]
    joined = parts[parts.plan.eq("authorized_2024_only")].merge(labels, on=KEYS)
    purged = joined[joined.partition.eq("purged_or_outside")]
    assert set(purged.fecha_inicio_semana_objetivo) == {date(2024, 3, 3), date(2024, 5, 5)}
    assert joined.loc[joined.partition.isin(["train", "validation", "test"]), "en_intervalo_autorizado"].all()
    for left, right in (("train", "validation"), ("validation", "test")):
        a, b = joined[joined.partition.eq(left)], joined[joined.partition.eq(right)]
        assert a.fecha_fin_semana_objetivo.max() < b.fecha_inicio_semana.min()
    assert not next(row for row in reports if row["name"] == "seasons_2023_2024")["both_classes_in_every_partition"]


def test_one_class_stays_ineligible_without_extending_interval():
    labels, _ = materialize_labels(fixture_panel(start=date(2022, 12, 18), size=108), authorization())
    _, reports = chronological_review(labels)
    assert all(row["status"] == "not_fit_missing_class" for row in reports)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def manifest(directory):
    write_json(directory / "integrity_manifest.private.json", {"outputs_sha256": {
        path.relative_to(directory).as_posix(): digest_path(path)
        for path in directory.rglob("*") if path.is_file() and path.name != "integrity_manifest.private.json"}})


@pytest.fixture
def fictional_scenario(tmp_path, monkeypatch):
    root = tmp_path
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
    (root / ".gitignore").write_text("data/\n", encoding="utf-8")
    options = {**DEFAULTS, "authorization": authorization()}
    sources = []
    for source_id in ("delivery_2020", "delivery_2021", "delivery_2022", "delivery_2023", "delivery_2024_2026"):
        path = root / f"data/raw/{source_id}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fictional_unchanged")
        sources.append(SourceAuthorization(source_id, "fictional-v1", path.resolve(), ("Sheet",), "fictional",
            enabled=True, approved_extract=True, uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
            evidence_ref="fictional", custodian_ref="fictional", confidentiality_ref="fictional", storage_policy_ref="fictional"))
    registry = SourceRegistry(tuple(sources))
    write_json(root / options["access_config"], {"fictional": True})
    panel = panel_fixture()
    for policy, scenario in (("expanded", "exploratory"), ("expanded", "conservative"), ("strict", "exploratory")):
        directory = root / options["phase5a_dir"] / policy / scenario
        directory.mkdir(parents=True)
        frame = panel.assign(escenario=scenario, panel_fechas=policy)
        frame.to_parquet(directory / "context.private.parquet", index=False)
        frame.to_parquet(directory / "labels.private.parquet", index=False)
        build_features(frame, static_fixture(), NEIGHBORS).to_parquet(directory / "predictors_retrospective.private.parquet", index=False)
    write_json(root / options["phase5a_dir"] / "metadata.private.json", {
        "calendar_version": "fictional", "analysis_period": {"start": "2022-12-18", "end": "2025-01-11"},
        "source_provenance": {}, "coverage_metadata": {"provenance": {"normalization": {"sources": [
            {"source_id": s.source_id, "source_version": s.source_version, "source_sha256": digest_path(s.path)} for s in sources]}}}})
    manifest(root / options["phase5a_dir"])
    write_json(root / options["phase5b_dir"] / "experiment_A.private.json", {
        "required": BASE, "optional": [], "training_enabled": False, "parameters": {"fictional": True}})
    manifest(root / options["phase5b_dir"])
    prefix = "sigard_ml.official.spatial_ml.assumed_scenario_pipeline."
    monkeypatch.setattr(prefix + "require_branch", lambda root: None)
    monkeypatch.setattr(prefix + "load_configuration", lambda *args: ({}, registry))
    monkeypatch.setattr(prefix + "EXPECTED_RADIOS", 2)
    monkeypatch.setattr(prefix + "EXPECTED_LABEL_COUNTS", class_counts(panel.objetivo_semana_siguiente))
    for target in ("sklearn.ensemble.RandomForestClassifier.fit", "sklearn.ensemble.RandomForestRegressor.fit",
                   "sklearn.impute.SimpleImputer.fit", "sigard_ml.official.excel.open_authorized_workbook"):
        monkeypatch.setattr(target, lambda *args, **kwargs: pytest.fail("No fit ni Excel en esta fase"))
    return root, options, registry


def test_pipeline_integrity_reproducibility_private_output_no_fit(fictional_scenario):
    root, options, registry = fictional_scenario
    inputs, output = paths(root, options)
    before = snapshot(inputs, registry)
    report = run_scenario(root, options)
    assert report["authorized_target_interval"] == {"rows": 44, "positive": 22, "negative": 22, "unknown": 0, "assumed_negative": 22}
    assert not report["training_performed"] and not report["counts_modified"]
    verify_private_manifest(output)
    require_preserved(before, snapshot(inputs, registry))
    assert (output / "experiment_A.reference.private.json").read_bytes() == (inputs["phase5b_dir"] / "experiment_A.private.json").read_bytes()
    with pytest.raises(ValueError, match="nuevo"):
        run_scenario(root, options)
    other = {**options, "output_dir": "data/processed/official/fictional_repeat"}
    assert run_scenario(root, other) == report
    for path in output.rglob("*.parquet"):
        assert digest_path(path) == digest_path(root / other["output_dir"] / path.name)


def test_tampering_blocks_before_writing(fictional_scenario):
    root, options, _ = fictional_scenario
    (root / options["phase5a_dir"] / "expanded/exploratory/labels.private.parquet").write_bytes(b"fictional_corruption")
    with pytest.raises(ValueError, match="manifiesto"):
        run_scenario(root, options)
    assert not (root / options["output_dir"]).exists()


def test_denied_source_stops_before_snapshot(fictional_scenario, monkeypatch):
    root, options, registry = fictional_scenario
    denied = SourceRegistry((replace(registry.sources[0], enabled=False), *registry.sources[1:]))
    prefix = "sigard_ml.official.spatial_ml.assumed_scenario_pipeline."
    monkeypatch.setattr(prefix + "load_configuration", lambda *args: ({}, denied))
    monkeypatch.setattr(prefix + "snapshot", lambda *args: pytest.fail("lectura sin autorización"))
    with pytest.raises(AccessDenied):
        run_scenario(root, options)


@pytest.mark.parametrize("changes", [{"training_enabled": True}, {"output_dir": "frontend/public/data"},
    {"output_dir": "../outside"}, {"phase5a_dir": "data/raw"}])
def test_unsafe_paths_or_training_rejected(tmp_path, changes):
    with pytest.raises(ValueError):
        paths(tmp_path, {**DEFAULTS, "authorization": authorization(), **changes})
