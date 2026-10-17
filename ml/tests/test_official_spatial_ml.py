"""Fase 5A: datos y geometrías ficticios; jamás usa la entrega oficial real."""

from dataclasses import replace
from datetime import date, timedelta
import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization, SourceRegistry
from sigard_ml.official.calendar import week_from_date
from sigard_ml.official.spatial_ml.dataset import build_dataset, territorial_context
from sigard_ml.official.spatial_ml.features import KEYS, build_features, exact_lag, feature_definitions
from sigard_ml.official.spatial_ml.diagnostics import diagnose
from sigard_ml.official.spatial_ml.pipeline import DEFAULTS, private_paths, report_text, run_preparation
from sigard_ml.official.spatial_ml.splits import prepare_splits
from sigard_ml.official.spatial_ml.validation import validate_panel
from sigard_ml.official.spatial_pipeline import digest_path, protected_snapshot, require_preserved
from sigard_ml.official.weekly_targets import attach_next_week_target

RADIOS = ["460140001", "460140002"]


def fixture_panel(counts=None, *, start=date(2023, 12, 17), size=16, scenario="conservative", policy="expanded"):
    rows = []
    for radio in RADIOS:
        values = counts[radio] if counts else [1] * size
        for i, count in enumerate(values):
            week = week_from_date(start + timedelta(weeks=i))
            zero = count == 0
            rows.append({"radio_censal": radio, "fecha_inicio_semana": week.start, "fecha_fin_semana": week.end,
                "anio_epidemiologico": week.year, "semana_epidemiologica": week.number,
                "casos_observados": count, "estado_observacion": "cero_comprobado_bajo_reglas" if zero else "positivo_provisional" if count else "sin_informacion_suficiente",
                "estado_cobertura": "completa_comprobada" if zero else "desconocida",
                "cobertura_comprobada": "complete" if zero else "unknown", "cero_provisional": False,
                "registros_pendientes_posibles": 0, "ventana_semanal_parcial": False,
                "registros_fecha_aproximada": 0, "registros_asignacion_incierta": count or 0,
                "validado": False, "escenario": scenario, "panel_fechas": policy})
    frame = pd.DataFrame(rows)
    frame["casos_observados"] = pd.array(frame.casos_observados, dtype="Int64")
    return attach_next_week_target(frame)


def static_fixture():
    return pd.DataFrame({"radio_censal": RADIOS, "superficie_km2": [1., 2.],
                         "poblacion": [100, 200], "densidad_poblacional": [100., 100.]})


NEIGHBORS = {RADIOS[0]: [RADIOS[1]], RADIOS[1]: [RADIOS[0]]}


def test_exact_lags_windows_and_availability_do_not_replace_unknown_by_zero():
    values = list(range(1, 17))
    panel = fixture_panel({RADIOS[0]: values, RADIOS[1]: values})
    result = build_features(panel, static_fixture(), NEIGHBORS)
    row = result.iloc[12]
    assert [row[f"registros_retro_rezago_{lag}"] for lag in range(1, 5)] == [12, 11, 10, 9]
    assert [row[f"registros_retro_acumulado_{window}"] for window in (4, 8, 12)] == [42, 68, 78]
    assert result.iloc[0].filter(like="acumulado").loc[lambda s: ~s.index.str.endswith("disponible")].isna().all()
    values[10] = None
    changed = build_features(fixture_panel({RADIOS[0]: values, RADIOS[1]: values}), static_fixture(), NEIGHBORS)
    row = changed.iloc[12]
    assert pd.isna(row.registros_retro_rezago_2)
    assert pd.isna(row.registros_retro_acumulado_4)
    assert row.registros_retro_semanas_conocidas_4 == 3
    assert not row.registros_retro_acumulado_4_valor_disponible


def test_neighbors_propagate_unknown_and_count_known_neighbors():
    a, b = [2] * 16, [3] * 16
    b[10] = None
    result = build_features(fixture_panel({RADIOS[0]: a, RADIOS[1]: b}), static_fixture(), NEIGHBORS)
    row = result.iloc[12]
    assert row.vecinos_retro_rezago_1 == 3
    assert pd.isna(row.vecinos_retro_rezago_2) and pd.isna(row.vecinos_retro_acumulado_4)
    assert row.vecinos_retro_conocidos_rezago_2 == 0
    assert row.vecinos_retro_semanas_conocidas_4 == 3
    no_neighbors = build_features(fixture_panel(), static_fixture(), {radio: [] for radio in RADIOS})
    assert no_neighbors.vecinos_retro_rezago_1.isna().all()
    assert no_neighbors.vecinos_retro_acumulado_12.isna().all()


def test_multiple_neighbors_require_every_neighbor_not_a_partial_sum():
    panel = fixture_panel({RADIOS[0]: [2] * 16, RADIOS[1]: [None] * 16})
    third = panel[panel.radio_censal.eq(RADIOS[0])].copy()
    third["radio_censal"] = "460140003"
    panel = pd.concat([panel, third], ignore_index=True)
    static = pd.concat([static_fixture(), static_fixture().iloc[:1].assign(radio_censal="460140003")])
    graph = {RADIOS[0]: [RADIOS[1], "460140003"], RADIOS[1]: [RADIOS[0]], "460140003": [RADIOS[0]]}
    row = build_features(panel, static, graph).iloc[12]
    assert row.cantidad_vecinos == 2 and row.vecinos_retro_conocidos_rezago_1 == 1
    assert pd.isna(row.vecinos_retro_rezago_1)


def test_supported_zero_is_preserved_in_local_and_neighbor_windows():
    panel = fixture_panel({radio: [0] * 16 for radio in RADIOS})
    result = build_features(panel, static_fixture(), NEIGHBORS)
    assert result.iloc[12].registros_retro_acumulado_12 == 0
    assert result.iloc[12].vecinos_retro_acumulado_12 == 0
    assert result.iloc[12].vecinos_retro_acumulado_12_valor_disponible


def test_lag_does_not_jump_missing_week_and_crosses_corrected_year():
    panel = fixture_panel()
    index = pd.MultiIndex.from_frame(panel[KEYS])
    values = pd.Series(pd.array(range(len(panel)), dtype="Int64"), index=index)
    new_year = (RADIOS[0], date(2023, 12, 31))
    assert exact_lag(values, index, 1).loc[new_year] == 1
    values = values.drop((RADIOS[0], date(2023, 12, 24)))
    assert pd.isna(exact_lag(values, index, 1).loc[new_year])
    result = build_features(panel, static_fixture(), NEIGHBORS)
    row = result[result.fecha_inicio_semana.eq(date(2023, 12, 31))].iloc[0]
    assert row.anio_epidemiologico == 2024 and row.semana_epidemiologica == 1
    assert row.estacionalidad_seno == 0 and row.estacionalidad_coseno == 1


def test_future_counts_labels_and_quality_cannot_change_origin_predictors():
    panel = fixture_panel()
    before = build_features(panel, static_fixture(), NEIGHBORS)
    changed = panel.copy()
    origin = date(2024, 1, 7)
    future = changed.fecha_inicio_semana.gt(origin)
    changed.loc[future, "casos_observados"] = 9876
    changed["objetivo_semana_siguiente"] = 0
    changed["registros_fecha_aproximada"] = 99
    after = build_features(changed, static_fixture(), NEIGHBORS)
    pd.testing.assert_frame_equal(before[before.fecha_inicio_semana.le(origin)], after[after.fecha_inicio_semana.le(origin)])
    assert not any("objetivo" in name or "coordenada" in name or "centroid" in name for name in after)
    assert not after.historia_disponible_en_origen_validada.any()
    assert not after.contexto_censal_disponible_en_origen_validado.any()


def test_labels_three_states_and_separation_of_calendar_features():
    panel = fixture_panel({radio: [2, 0, None, 4] for radio in RADIOS})
    period = {"start": "2023-12-17", "end": "2024-01-13"}
    tables = build_dataset(panel, static_fixture(), NEIGHBORS, period)
    labels = tables["labels"].objetivo_semana_siguiente
    assert labels.iloc[:2].tolist() == [0, pd.NA]  # Unknown remains nullable.
    assert labels.iloc[2] == 1 and pd.isna(labels.iloc[3])
    assert not tables["labels"].apto_entrenamiento.any()
    assert not any(name.startswith("registros") or name in ("poblacion", "densidad_poblacional") for name in tables["predictors_calendar"])


@pytest.mark.parametrize("mutation", ["year", "gap", "duplicate", "zero", "target"])
def test_validation_rejects_inconsistent_calendar_grid_zeros_and_targets(mutation):
    panel = fixture_panel()
    if mutation == "year":
        panel.loc[2, "anio_epidemiologico"] = 2023
    elif mutation == "gap":
        panel = panel.drop(index=2)
    elif mutation == "duplicate":
        panel = pd.concat([panel, panel.iloc[:1]])
    elif mutation == "zero":
        panel.loc[2, "casos_observados"] = 0
    else:
        panel.loc[2, "objetivo_semana_siguiente"] = 0
    with pytest.raises((ValueError, AssertionError)):
        validate_panel(panel, set(RADIOS), {"start": "2023-12-17", "end": "2024-04-06"})


def geographical_fixture():
    radios = gpd.GeoDataFrame({"radio_id": RADIOS, "poblacion": [100, 200],
        "neighbor_ids": [[RADIOS[1]], [RADIOS[0]]]},
        geometry=[box(500000, 6680000, 501000, 6681000), box(501000, 6680000, 502000, 6681000)], crs=32719)
    radios["superficie_km2"] = radios.area / 1e6
    radios["densidad_poblacional"] = radios.poblacion / radios.superficie_km2
    return radios.to_crs(4326)


def test_geographic_relationships_are_verified_and_population_is_real_context():
    static, graph = territorial_context(geographical_fixture(), expected_count=2)
    assert graph == NEIGHBORS and static.poblacion.tolist() == [100, 200]


@pytest.mark.parametrize("mutation", ["missing_edge", "self", "asymmetric", "density", "population"])
def test_invalid_graph_and_census_values_are_not_invented(mutation):
    radios = geographical_fixture()
    if mutation == "missing_edge":
        radios["neighbor_ids"] = [[], []]
    elif mutation == "self":
        radios.at[0, "neighbor_ids"] = [RADIOS[0]]
    elif mutation == "asymmetric":
        radios.at[0, "neighbor_ids"] = []
    elif mutation == "density":
        radios.loc[0, "densidad_poblacional"] = 99999
    else:
        radios.loc[0, "poblacion"] = None
    with pytest.raises(ValueError):
        territorial_context(radios, expected_count=2)


PLANS = [{"name": "fictional", "validation_start": "2024-01-07", "test_start": "2024-02-04", "end": "2024-03-31"}]


def test_chronological_splits_purge_boundaries_and_keep_unknown_out_of_negatives():
    panel = fixture_panel({radio: [None, 1, 0, 1] * 4 for radio in RADIOS})
    assignments, report = prepare_splits(panel, PLANS)
    merged = assignments.merge(panel, on=KEYS)
    for partition, boundary in (("train", date(2024, 1, 7)), ("validation", date(2024, 2, 4)), ("test", date(2024, 3, 31))):
        selected = merged[merged.partition.eq(partition)]
        assert (selected.fecha_inicio_semana_objetivo.map(lambda day: day + timedelta(days=6)) < boundary).all()
        stats = report[0]["partitions"][partition]
        assert stats["positive"] + stats["negative"] + stats["unknown"] == stats["rows"]
    for day in (date(2023, 12, 31), date(2024, 1, 28)):
        assert assignments.loc[assignments.fecha_inicio_semana.eq(day), "partition"].eq("purged_or_outside").all()
    assert not report[0]["fit_for_training"] and not assignments.eligible_for_future_supervised_use.any()
    _, no_negative = prepare_splits(fixture_panel(), PLANS)
    assert not no_negative[0]["both_classes_in_every_partition"]


def test_reproducibility_and_input_immutability(tmp_path):
    panel, static = fixture_panel(), static_fixture()
    preserved = panel.copy(deep=True)
    first = build_features(panel, static, NEIGHBORS)
    second = build_features(panel.sample(frac=1, random_state=19), static, NEIGHBORS)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(panel, preserved)
    first.to_parquet(tmp_path / "first.parquet", index=False)
    second.to_parquet(tmp_path / "second.parquet", index=False)
    assert digest_path(tmp_path / "first.parquet") == digest_path(tmp_path / "second.parquet")


def test_corrected_2025_week_53_transitions_to_2026_week_1():
    panel = fixture_panel(start=date(2025, 12, 21), size=4)
    tables = build_dataset(panel, static_fixture(), NEIGHBORS, {"start": "2025-12-21", "end": "2026-01-17"})
    features = tables["predictors_retrospective"]
    assert features.iloc[:4].semana_epidemiologica.tolist() == [52, 53, 1, 2]
    assert features.iloc[2].anio_epidemiologico == 2026 and features.iloc[2].registros_retro_rezago_1 == 1
    assert tables["labels"].iloc[1].fecha_inicio_semana_objetivo == date(2026, 1, 4)
    definitions = feature_definitions(features.columns)
    assert definitions["radio_censal"]["kind"] == "categorical_territorial_identifier"
    assert definitions["registros_retro_acumulado_4"]["source_week_offsets"] == [-4, -3, -2, -1]
    assert all(max(value["source_week_offsets"]) <= 0 for value in definitions.values() if value.get("source_week_offsets"))


@pytest.mark.parametrize("value", [None, 0])
def test_diagnostics_never_interpret_a_radio_without_positive_records_as_positive(value):
    panel = fixture_panel({radio: [value] * 16 for radio in RADIOS})
    features = build_features(panel, static_fixture(), NEIGHBORS)
    audit = pd.DataFrame({"source_id": ["fictional"], "classification": ["indeterminado"],
                          "processing_outcome": ["excluded"], "fecha_aproximada": [False]})
    diagnostics, summary = diagnose(panel, features, audit)
    assert summary["radios_without_positive_records"] == 2
    assert summary["records_2024_fraction"] is None
    _, plans = prepare_splits(panel, PLANS)
    text = report_text({"datasets": {"fixture": summary}, "splits": {"fixture": plans}}, {"fixture": diagnostics})
    assert "no definida" in text


@pytest.mark.parametrize("path", ["data/interim/official/observed", "frontend/public/data", "data/processed/official", "../outside"])
def test_output_is_private_new_and_separate(tmp_path, path):
    with pytest.raises(ValueError):
        private_paths(tmp_path, {**DEFAULTS, "output_dir": path})


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def manifest(directory, private=False, protected=None):
    save_json(directory / ("integrity_manifest.private.json" if private else "integrity_manifest.json"), {
        "outputs_sha256": {path.relative_to(directory).as_posix(): digest_path(path) for path in directory.rglob("*") if path.is_file()},
        "protected_files_sha256": protected or {}})


@pytest.fixture
def fictional_preparation(tmp_path, monkeypatch):
    root = tmp_path
    options = {**DEFAULTS, "split_plans": PLANS}
    source_path = root / "data/raw/fictional.bin"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"FICTIONAL_OFFICIAL_INPUT_UNCHANGED")
    source = SourceAuthorization("fixture", "v1", source_path.resolve(), ("Sheet",), "fictional",
        enabled=True, approved_extract=True, uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
        evidence_ref="fictional", custodian_ref="fictional", confidentiality_ref="fictional", storage_policy_ref="fictional")
    registry = SourceRegistry((source,))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.pipeline.require_branch", lambda root: None)
    monkeypatch.setattr("sigard_ml.official.spatial_ml.pipeline.load_configuration", lambda *args: ({}, registry))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.pipeline.territorial_context", lambda frame: territorial_context(frame, expected_count=2))
    monkeypatch.setattr("sigard_ml.official.excel.open_authorized_workbook", lambda *args: pytest.fail("Fase 5A no debe abrir Excel"))
    save_json(root / options["access_config"], {"fictional": True})
    master = root / options["cartography"]
    master.parent.mkdir(parents=True)
    geographical_fixture().to_parquet(master, index=False)
    quality = root / "data/processed/fictional_quality.json"
    save_json(quality, {"joins": {"all_sources_one_to_one": True}, "output": {"rows": 263}})
    save_json(root / options["territorial_config"], {"outputs": {"quality_report": quality.relative_to(root).as_posix()},
        "sources": {name: {"path": source_path.relative_to(root).as_posix()} for name in ("population", "cartography")}})
    normalization = {"sources": [{"source_id": "fixture", "source_version": "v1", "source_sha256": digest_path(source_path)}]}
    metadata = {"provenance": {"normalization": normalization}, "analysis_period": {"start": "2023-12-17", "end": "2024-04-06"}}
    for policy in ("strict", "expanded"):
        audit = pd.DataFrame({"source_id": ["fixture"] * 32, "classification": ["confirmado"] * 32,
                              "processing_outcome": ["included"] * 32, "fecha_aproximada": [False] * 32})
        prior = root / options["observed_dir"] / policy / "exploratory"
        save_json(prior / "metadata.json", metadata)
        audit.to_parquet(prior / "records_audit.parquet", index=False)
        manifest(prior)
        for scenario in ("conservative", "exploratory"):
            directory = root / options["coverage_dir"] / policy / scenario
            directory.mkdir(parents=True)
            fixture_panel(scenario=scenario, policy=policy).to_parquet(directory / "panel.parquet", index=False)
    manifest(root / options["observed_dir"])
    save_json(root / options["coverage_dir"] / "metadata.json", metadata)
    manifest(root / options["coverage_dir"])
    geo = root / options["geography_dir"]
    save_json(geo / "geographic_quality.json", {"cartography": {"master_sha256": digest_path(master)}})
    manifest(geo, protected={str(path.relative_to(root)): digest_path(path) for path in (master, quality, source_path)})
    universe = root / options["universe_dir"]
    save_json(universe / "review.private.json", {"provenance": normalization, "supporting_reports_sha256": {},
        **{key: {} for key in ("universe", "uncertainty", "previous_delay_evidence", "previous_geographic_sensitivity", "geographic_evidence")}})
    manifest(universe, private=True)
    return root, options, registry


def test_full_private_pipeline_integrity_reproducibility_and_no_overwrite(fictional_preparation):
    root, options, _ = fictional_preparation
    output = root / options["output_dir"]
    before = protected_snapshot(root, output)
    report = run_preparation(root, options)
    assert not report["training_ready"] and not report["artificial_zeros_generated"]
    assert report["datasets"]["expanded/conservative"]["labels"]["negative"] == 0
    require_preserved(before, protected_snapshot(root, output))
    with pytest.raises(ValueError, match="sobrescribir"):
        run_preparation(root, options)
    second = {**options, "output_dir": "data/processed/official/fictional_repeat"}
    repeated = run_preparation(root, second)
    assert report == repeated
    for path in output.rglob("*.parquet"):
        assert digest_path(path) == digest_path(root / second["output_dir"] / path.relative_to(output))
    assert "FICTIONAL_OFFICIAL_INPUT" not in (output / "implementation.private.md").read_text(encoding="utf-8")


def test_denied_access_stops_before_private_data_reads(fictional_preparation, monkeypatch):
    root, options, registry = fictional_preparation
    denied = SourceRegistry((replace(registry.sources[0], enabled=False),))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.pipeline.load_configuration", lambda *args: ({}, denied))
    monkeypatch.setattr("sigard_ml.official.spatial_ml.pipeline.protected_snapshot", lambda *args: pytest.fail("No leer sin permiso"))
    with pytest.raises(AccessDenied):
        run_preparation(root, options)


def test_tampered_prior_artifact_blocks_generation(fictional_preparation):
    root, options, _ = fictional_preparation
    artifact = root / options["coverage_dir"] / "expanded/conservative/panel.parquet"
    artifact.write_bytes(b"FICTIONAL_CORRUPTION")
    with pytest.raises(ValueError, match="manifiesto"):
        run_preparation(root, options)
    assert not (root / options["output_dir"]).exists()
