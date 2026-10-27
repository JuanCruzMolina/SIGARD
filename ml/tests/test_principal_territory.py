"""Unidades y polígonos inventados en memoria; sin fuentes ni casos reales."""

from datetime import date
import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from sigard_ml.forecasting.adapter import territorial_components
from sigard_ml.forecasting.contracts import ForecastError
from sigard_ml.ingestion.territorial import add_spatial_metrics
from sigard_ml.territorial.universe import build_universe, create_version, graph_edges, load_version, sha256


def fixture(count=4):
    # Rectángulos inventados de 10 x 10 m; ninguna cartografía o distribución real.
    master = gpd.GeoDataFrame(dict(radio_id=[f"46014{i:04d}" for i in range(count)],
                                  poblacion=list(range(1, count + 1)), hogares=[1] * count,
                                  viviendas=[1] * count),
        geometry=[box(700000 + i * 10, 6700000, 700010 + i * 10, 6700010) for i in range(count)], crs=32719)
    master = add_spatial_metrics(master, "EPSG:32719", "EPSG:32719")
    master["densidad_poblacional"] = master.poblacion / master.superficie_km2
    inside, near = (245, 11) if count == 263 else (1, 1)
    fractions = [1.] * inside + [0.9999] * near + [0.5] + [0.] * (count - inside - near - 1)
    comparison = pd.DataFrame(dict(radio_id=master.radio_id, locality_code="46014010",
        relation=["inside"] * inside + ["partial"] * (near + 1) + ["outside"] * (count - inside - near - 1),
        intersection_fraction_raw=fractions, radio_area_m2=100.,
        intersection_area_m2=[100 * value for value in fractions],
        outside_area_m2=[100 * (1 - value) for value in fractions],
        metric_crs="EPSG:32719", transformation_version="locality-radio-comparison-1"))
    config = dict(territory_version="fictional_territory_v1", transformation_version="whole-radio-locality-selection-1",
        locality_code="46014010", minimum_inside_fraction=0.9999,
        expected_counts=dict(source=count, inside=inside, near_complete=near, selected=inside + near,
                             excluded=count - inside - near),
        decision=dict(status="approved_operational_scope", epidemiological_eligibility=False,
                      historical_availability_accredited=False),
        output_directory="data/processed/fictional_territory_v1")
    return master, comparison, config


def stage(tmp_path):
    master, comparison, config = fixture()
    folder = tmp_path / "data/interim/fictional"
    folder.mkdir(parents=True)
    master.to_parquet(folder / "master.parquet", index=False)
    comparison.to_csv(folder / "comparison.csv", index=False)
    config["inputs"] = {name: dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256(path))
                        for name, path in (("master", folder / "master.parquet"),
                                           ("comparison", folder / "comparison.csv"))}
    return master, comparison, config


def test_exact_256_unique_whole_units_and_induced_graph_preserve_inputs():
    master, comparison, config = fixture(263)
    before, original_comparison = master.copy(deep=True), comparison.copy(deep=True)
    selected, report = build_universe(master.iloc[::-1], comparison.iloc[::-1], config)
    assert len(selected) == selected.radio_id.nunique() == 256
    assert report["counts"] == dict(source=263, inside=245, near_complete=11, selected=256, excluded=7)
    pd.testing.assert_frame_equal(selected.drop(columns="neighbor_ids"),
                                  master.iloc[:256].reset_index(drop=True).drop(columns="neighbor_ids"))
    ids = set(selected.radio_id)
    assert all(a in ids and b in ids and (b, a) in graph_edges(selected) for a, b in graph_edges(selected))
    assert report["excluded_neighbor_references_removed"] == 1
    assert report["graph_components"] == 1 and report["isolated_radios"] == 0
    assert not report["counts_created"] and not report["patient_assignments_modified"]
    pd.testing.assert_frame_equal(master, before)
    pd.testing.assert_frame_equal(comparison, original_comparison)


def test_inclusive_threshold_has_no_rounding_or_type_rule():
    master, comparison, config = fixture()
    comparison["radio_type"] = "irrelevant_to_approved_selection"
    selected, _ = build_universe(master, comparison, config)
    assert selected.radio_id.tolist() == master.radio_id.iloc[:2].tolist()
    comparison.loc[1, "intersection_fraction_raw"] = 0.999899999
    comparison.loc[1, "intersection_area_m2"] = 99.9899999
    comparison.loc[1, "outside_area_m2"] = 0.0100001
    with pytest.raises(ValueError, match="Cantidad seleccionada"):
        build_universe(master, comparison, config)


@pytest.mark.parametrize("failure", ["duplicate", "foreign_id", "wrong_locality", "wrong_crs", "wrong_version",
    "nan", "infinite", "wrong_area", "wrong_fraction", "wrong_relation", "wrong_threshold", "wrong_count",
    "invalid_geometry", "null_geometry", "wrong_population", "wrong_density", "wrong_surface",
    "foreign_neighbor", "asymmetry", "duplicate_edge", "missing_edge", "no_approval", "epidemiology_approval"])
def test_invalid_context_or_selection_fails_closed(failure):
    master, comparison, config = fixture()
    if failure == "duplicate": comparison.loc[1, "radio_id"] = comparison.loc[0, "radio_id"]
    elif failure == "foreign_id": comparison.loc[0, "radio_id"] = "fictional_foreign"
    elif failure == "wrong_locality": comparison.loc[0, "locality_code"] = "fictional_other"
    elif failure == "wrong_crs": comparison.loc[0, "metric_crs"] = "EPSG:3857"
    elif failure == "wrong_version": comparison.loc[0, "transformation_version"] = "fictional_other"
    elif failure == "nan": comparison.loc[0, "intersection_fraction_raw"] = float("nan")
    elif failure == "infinite": comparison.loc[0, "intersection_area_m2"] = float("inf")
    elif failure == "wrong_area": comparison.loc[0, "radio_area_m2"] = 200
    elif failure == "wrong_fraction": comparison.loc[0, "intersection_fraction_raw"] = .9
    elif failure == "wrong_relation": comparison.loc[0, "relation"] = "outside"
    elif failure == "wrong_threshold": config["minimum_inside_fraction"] = .5
    elif failure == "wrong_count": config["expected_counts"]["selected"] = 3
    elif failure == "invalid_geometry": master.loc[0, "geometry"] = box(0, 0, 0, 0)
    elif failure == "null_geometry": master.loc[0, "geometry"] = None
    elif failure == "wrong_population": master.loc[0, "poblacion"] = -1
    elif failure == "wrong_density": master.loc[0, "densidad_poblacional"] = 0
    elif failure == "wrong_surface": master.loc[0, "superficie_km2"] = 1
    elif failure == "foreign_neighbor": master.at[0, "neighbor_ids"] = ["fictional_foreign"]
    elif failure == "asymmetry": master.at[0, "neighbor_ids"] = []
    elif failure == "duplicate_edge": master.at[0, "neighbor_ids"] *= 2
    elif failure == "missing_edge":
        master.at[0, "neighbor_ids"] = []
        master.at[1, "neighbor_ids"] = [master.radio_id.iloc[2]]
    elif failure == "no_approval": config["decision"]["status"] = "pending"
    else: config["decision"]["epidemiological_eligibility"] = True
    with pytest.raises(ValueError):
        build_universe(master, comparison, config)


def test_version_roundtrip_and_adapter_require_explicit_availability(tmp_path):
    master, _, config = stage(tmp_path)
    before = {name: sha256(tmp_path / item["path"]) for name, item in config["inputs"].items()}
    create_version(config, tmp_path)
    frame = load_version(config, tmp_path)
    components = territorial_components(config, tmp_path, available_on=date(2030, 1, 1),
        source_ref="fictional_territory", graph_available_on=date(2030, 1, 2), graph_ref="fictional_graph")
    assert components["radios"] == tuple(frame.radio_id)
    assert set(components["territory"]) == {"radio_id", "population", "area_km2", "available_on", "source_ref"}
    assert components["territory"].population.tolist() == master.poblacion.iloc[:2].tolist()
    assert components["graph"]["available_on"] == date(2030, 1, 2)
    assert set(components) == {"territory_version", "radios", "territory", "graph"}
    with pytest.raises(ForecastError, match="fecha sin hora"):
        territorial_components(config, tmp_path, available_on=None, source_ref="fictional_territory",
            graph_available_on=date(2030, 1, 2), graph_ref="fictional_graph")
    with pytest.raises(ValueError, match="No sobrescribir"):
        create_version(config, tmp_path)
    assert before == {name: sha256(tmp_path / item["path"]) for name, item in config["inputs"].items()}


@pytest.mark.parametrize("failure", ["input_hash", "output_hash", "configuration", "graph", "output_escape"])
def test_integrity_configuration_and_safe_paths(tmp_path, failure):
    _, _, config = stage(tmp_path)
    if failure == "input_hash":
        config["inputs"]["comparison"]["sha256"] = "0" * 64
        with pytest.raises(ValueError, match="Integridad de entrada"):
            create_version(config, tmp_path)
        return
    if failure == "output_escape":
        config["output_directory"] = "data/raw/fictional"
        with pytest.raises(ValueError, match="Ruta territorial"):
            create_version(config, tmp_path)
        return
    create_version(config, tmp_path)
    output = tmp_path / config["output_directory"]
    if failure == "configuration": config["territory_version"] = "fictional_other"
    elif failure == "output_hash": (output / "graph.json").write_text("{}")
    else:
        graph = json.loads((output / "graph.json").read_text())
        graph["edges"] = []
        (output / "graph.json").write_text(json.dumps(graph))
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["outputs_sha256"]["graph.json"] = sha256(output / "graph.json")
        (output / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Configuración|Integridad|Grafo"):
        load_version(config, tmp_path)
