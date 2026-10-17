"""Todas las posiciones, fuentes y geometrías de estas pruebas son ficticias."""

import json
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon, box
from openpyxl import Workbook

from sigard_ml.official.cartography import audit_cartography, compare_reference, validate_radios
from sigard_ml.official.spatial_assignment import assign_coordinates
from sigard_ml.official.spatial_pipeline import (
    assignment_options, digest_path, private_output_directory, protected_snapshot,
    read_authorized_normalized, require_preserved, run_spatial_diagnostics,
)
from sigard_ml.official.spatial_reports import boundary_sensitivity, geographic_quality
from sigard_ml.official.spatial_settings import SPATIAL_DEFAULTS
from sigard_ml.official.pipeline import load_configuration, validate_delivery
from sigard_ml.official.reports import write_report


@pytest.fixture
def radios():
    return gpd.GeoDataFrame({"radio_id": ["460140001", "460140002"]},
                           geometry=[box(-67, -30, -66.999, -29.999),
                                     box(-66.999, -30, -66.998, -29.999)], crs=4326)


def records(coordinates, **columns):
    size = len(coordinates)
    return pd.DataFrame({"record_ref": [f"fictional_{i}" for i in range(size)],
                         "source_id": ["fixture"] * size, "sheet_ref": ["sheet_01"] * size,
                         "longitude_candidate": [point[0] for point in coordinates],
                         "latitude_candidate": [point[1] for point in coordinates], **columns})


def assign(frame, radios, **options):
    return assign_coordinates(frame, radios, expected_count=len(radios), **options)


def test_interior_has_unique_candidate_but_unknown_accuracy(radios):
    result = assign(records([(-66.9995, -29.9995)]), radios).iloc[0]
    assert result.geometry_status == "unique_interior"
    assert result.radio_candidate == "460140001"
    assert result.assignment_state == "uncertain"
    assert "crs_unconfirmed" in result.uncertainty_reasons
    assert "positional_accuracy_undocumented" in result.uncertainty_reasons
    assert not result.epidemiological_precision_validated


def test_documented_interior_can_be_geometrically_unique(radios):
    result = assign(records([(-66.9995, -29.9995)], coordinate_precision_label=["rooftop"]),
                    radios, crs_confirmed=True, documented_uncertainty_m=1,
                    uncertainty_evidence_ref="fictional_error_study", location_role="residence",
                    geocoding_provenance_ref="fictional_method").iloc[0]
    assert result.assignment_state == "unique_geometry"
    assert not result.epidemiological_precision_validated


def test_outside_is_never_assigned_even_with_review_distance(radios):
    result = assign(records([(-67.00001, -29.9995)]), radios, boundary_review_m=100).iloc[0]
    assert result.geometry_status == "outside_territory"
    assert result.assignment_state == "unassigned"
    assert result.radio_candidate is None


def test_shared_boundary_is_ambiguous_and_has_no_candidate(radios):
    result = assign(records([(-66.999, -29.9995)]), radios).iloc[0]
    assert result.assignment_state == "ambiguous"
    assert result.matching_radios == ["460140001", "460140002"]
    assert result.radio_candidate is None


def test_outer_boundary_without_second_polygon_is_ambiguous(radios):
    result = assign(records([(-67, -29.9995)]), radios).iloc[0]
    assert result.geometry_status == "boundary"
    assert result.assignment_state == "ambiguous" and result.radio_candidate is None


def test_near_boundary_measured_in_metres_and_scenario_alternatives(radios):
    result = assign(records([(-66.99901, -29.9995)]), radios, boundary_review_m=10).iloc[0]
    assert 0 < result.distance_to_boundary_m < 2
    assert "near_boundary_review_scenario" in result.uncertainty_reasons
    assert result.alternative_radios == ["460140001", "460140002"]
    assert result.alternative_basis == "review_scenario"


@pytest.mark.parametrize("coordinate, expected", [((None, -30), "missing_coordinates"),
                                                  ((None, None), "missing_coordinates"),
                                                  (("invalid", -30), "invalid_coordinates"),
                                                  ((300, -30), "invalid_coordinates"),
                                                  ((float("inf"), -30), "invalid_coordinates")])
def test_unusable_coordinates_are_retained_without_positions(radios, coordinate, expected):
    result = assign(records([coordinate]), radios).iloc[0]
    assert result.geometry_status == expected and result.assignment_state == "unassigned"
    assert result.radio_candidate is None and result.coordinate_group_ref is None


def test_repetition_across_sheets_is_diagnostic_not_deduplication(radios):
    frame = records([(-66.9995, -29.9995)] * 2, sheet_ref=["sheet_01", "sheet_02"])
    result = assign(frame, radios)
    assert len(result) == 2 and result.coordinate_group_ref.nunique() == 1
    assert result.coordinate_group_size.tolist() == [2, 2]
    assert all("shared_coordinate_review" in reasons for reasons in result.uncertainty_reasons)


def test_unknown_and_unsupported_crs_do_not_assign(radios):
    frame = records([(-66.9995, -29.9995)])
    result = assign(frame, radios, coordinate_crs=None).iloc[0]
    assert result.geometry_status == "unknown_crs" and result.radio_candidate is None
    with pytest.raises(ValueError, match="CRS"):
        assign(frame, radios, coordinate_crs="EPSG:3857", crs_confirmed=True)
    with pytest.raises(ValueError, match="proyectadas"):
        assign(frame, radios, coordinate_crs="EPSG:32719")


def test_confirmed_projected_input_is_transformed_and_wrong_units_never_match(radios):
    projected = gpd.GeoSeries([Point(-66.9995, -29.9995)], crs=4326).to_crs(32719).iloc[0]
    result = assign(records([(projected.x, projected.y)]), radios,
                    coordinate_crs="EPSG:32719", crs_confirmed=True).iloc[0]
    assert result.geometry_status == "unique_interior" and result.radio_candidate == "460140001"
    wrong = assign(records([(-66.9995, -29.9995)]), radios,
                   coordinate_crs="EPSG:32719", crs_confirmed=True).iloc[0]
    assert wrong.assignment_state == "unassigned" and wrong.radio_candidate is None


def test_invalid_geometry_is_rejected_without_repair(radios):
    invalid = radios.copy()
    invalid.loc[0, "geometry"] = Polygon([(-67, -30), (-66.999, -29.999),
                                          (-67, -29.999), (-66.999, -30), (-67, -30)])
    original = invalid.geometry.iloc[0].wkb
    with pytest.raises(ValueError, match="Geometría"):
        assign(records([(-66.9995, -29.9995)]), invalid)
    assert invalid.geometry.iloc[0].wkb == original


def test_multiple_interior_matches_never_choose_first(radios):
    overlap = radios.copy()
    overlap.loc[1, "geometry"] = box(-66.99975, -30, -66.99875, -29.999)
    report = audit_cartography(overlap, expected_count=2)
    assert report["positive_area_overlap_pairs"] == 1
    result = assign(records([(-66.9996, -29.9995)]), overlap).iloc[0]
    assert result.geometry_status == "multiple_matches"
    assert result.assignment_state == "ambiguous" and result.radio_candidate is None


def test_duplicate_polygons_and_wrong_territory_ids_rejected(radios):
    duplicate = radios.copy()
    duplicate.loc[1, "geometry"] = duplicate.geometry.iloc[0]
    with pytest.raises(ValueError, match="duplicados"):
        audit_cartography(duplicate, expected_count=2)
    wrong = radios.copy()
    wrong.loc[0, "radio_id"] = "999990001"
    with pytest.raises(ValueError, match="Capital"):
        validate_radios(wrong, expected_count=2)


def test_crs_missing_count_and_utm_extent_fail(radios):
    with pytest.raises(ValueError, match="CRS"):
        validate_radios(radios.set_crs(None, allow_override=True), expected_count=2)
    with pytest.raises(ValueError, match="Cantidad"):
        validate_radios(radios, expected_count=263)
    moved = radios.copy()
    moved.geometry = moved.geometry.translate(xoff=50)
    with pytest.raises(ValueError, match="área de uso"):
        audit_cartography(moved, expected_count=2)
    with pytest.raises(ValueError, match="área de uso"):
        audit_cartography(radios.set_crs(32719, allow_override=True), expected_count=2)


def test_small_utm_zone_extension_is_quantified_not_hidden(radios):
    extended = radios.copy()
    extended.geometry = extended.geometry.translate(xoff=1.4)
    report = audit_cartography(extended, expected_count=2)
    assert not report["nominal_metric_area_contains_entire_territory"]
    assert report["metric_scale_tolerance_verified"]
    assert 0 < report["bounding_box_max_scale_deviation_pct"] < report["diagnostic_scale_tolerance_pct"]


def test_reference_geometry_comparison_detects_change(radios):
    compare_reference(radios, radios.copy())
    changed = radios.copy()
    changed.loc[0, "geometry"] = box(-67, -30, -66.9991, -29.999)
    with pytest.raises(ValueError, match="origen"):
        compare_reference(changed, radios)


def test_reproducible_assignment_and_preserved_inputs(radios):
    frame = records([(-66.9995, -29.9995), (-66.999, -29.9995), (None, None)])
    original = frame.copy(deep=True)
    original_wkb = radios.geometry.to_wkb().tolist()
    first = assign(frame, radios, boundary_review_m=10)
    second = assign(frame, radios.iloc[::-1], boundary_review_m=10)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(frame, original)
    assert radios.geometry.to_wkb().tolist() == original_wkb


def test_eligibility_and_sensitive_columns_are_independent_of_geometry(radios):
    frame = records([(-66.9995, -29.9995)] * 3,
                    eligibility=["unresolved", "excluded", "eligible_episode"],
                    address=["FICTIONAL_PRIVATE_ADDRESS"] * 3,
                    classification_label=["Confirmado"] * 3)
    result = assign(frame, radios)
    assert result.eligibility.tolist() == frame.eligibility.tolist()
    assert result.geometry_status.eq("unique_interior").all()
    assert "classification_label" not in result and "address" not in result
    assert "latitude_candidate" not in result and "longitude_candidate" not in result
    assert "FICTIONAL_PRIVATE_ADDRESS" not in result.to_json()
    assert assign(frame.drop(columns="eligibility"), radios).eligibility.eq("unresolved").all()


def test_small_groups_are_suppressed_and_labels_never_echoed(radios):
    frame = records([(-66.9995, -29.9995), (-66.99901, -29.9995)],
                    coordinate_precision_label=["FICTIONAL_PRIVATE_LABEL", "calle"])
    result = assign(frame, radios)
    probes = boundary_sensitivity(frame, result, radios, "EPSG:4326", [10, 100])
    report = geographic_quality(result, probes)
    assert report["records_analyzed"] == "<5"
    assert report["unique_coordinates"] == "<5"
    assert report["geocoding_categories"]["other_or_mixed"] == "<5"
    assert "FICTIONAL_PRIVATE_LABEL" not in json.dumps(report)
    assert not report["case_counts_generated"] and not report["training_labels_generated"]


def test_undocumented_radius_and_negative_threshold_are_rejected(radios):
    with pytest.raises(ValueError, match="evidencia"):
        assign(records([(-66.9995, -29.9995)]), radios, documented_uncertainty_m=10)
    with pytest.raises(ValueError, match="Distancia"):
        assign(records([(-66.9995, -29.9995)]), radios, boundary_review_m=-1)


def test_private_output_paths_and_immutable_snapshots(tmp_path):
    options = dict(SPATIAL_DEFAULTS)
    for folder in ("data/processed/official", "frontend/public/data", "data/interim/official", "data/interim/official/normalized", "../outside"):
        options["output_dir"] = folder
        with pytest.raises(ValueError):
            private_output_directory(options, tmp_path)
    options["output_dir"] = SPATIAL_DEFAULTS["output_dir"]
    output = private_output_directory(options, tmp_path)
    source = tmp_path / "data/raw/fictional.txt"
    source.parent.mkdir(parents=True)
    source.write_text("original", encoding="utf-8")
    before = protected_snapshot(tmp_path, output)
    require_preserved(before, protected_snapshot(tmp_path, output))
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="protegido"):
        require_preserved(before, protected_snapshot(tmp_path, output))


def test_phase2_coordinate_contract_rejects_wrong_confirmed_crs():
    with pytest.raises(ValueError, match="EPSG:4326"):
        assignment_options({"geography": {"crs_confirmed": True, "crs": "EPSG:32719"}}, SPATIAL_DEFAULTS)


@pytest.fixture
def fictional_delivery(tmp_path):
    """Entrega mínima autorizada con 263 polígonos inventados; nunca datos reales."""
    source_root = tmp_path / "data/datos oficiales"
    source_root.mkdir(parents=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fictional"
    sheet.append(["ID Evento", "Clasificacion Manual", "Fecha Inicio Sintomas", "Latitud", "Longitud",
                  "Precision Geocodificacion", "Nombre"])
    for index, point in enumerate([(-66.9995, -29.9995), (-66.999, -29.9995), (None, None)]):
        sheet.append([f"fictional_event_{index}", "Confirmado", "2024-01-07", point[1], point[0],
                      "calle", "FICTIONAL_PRIVATE_PERSON"])
    source_path = source_root / "fictional.xlsx"
    workbook.save(source_path)
    config = {"source_root": str(source_root), "output_dir": str(tmp_path / "data/interim/official"),
              "uses": ["inspection", "processing"], "as_of_date": "2024-12-31", "write_normalized": True,
              "authorization": {name: "fictional_evidence" for name in
                                ("evidence_ref", "custodian_ref", "confidentiality_ref", "storage_policy_ref")},
              "sources": [{"source_id": "fixture", "filename": source_path.name, "source_version": "fixture_v1",
                           "enabled": True, "approved_extract": True, "sheets": ["Fictional"]}],
              "geography": {"crs_confirmed": False, "crs": None}}
    config_path = tmp_path / "data/interim/official/access.private.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    config, registry = load_configuration(config_path, tmp_path)
    write_report(validate_delivery(config, registry), config_path.parent / "quality_report.json")
    numbers = range(1, 264)
    master = gpd.GeoDataFrame({"radio_id": [f"46014{i:04d}" for i in numbers],
                              "provincia": ["LA RIOJA"] * 263, "departamento": ["Capital"] * 263},
                             geometry=[box(-67 + (i - 1) * .001, -30, -67 + i * .001, -29.999)
                                       for i in numbers], crs=4326)
    processed = tmp_path / "data/processed"
    processed.mkdir()
    master.to_parquet(processed / "territorial_master.parquet", index=False)
    reference = master.rename(columns={"radio_id": "LINK", "provincia": "NOMPROV", "departamento": "NOMDEPTO"})
    reference["PROV"], reference["DEPTO"] = "46", "014"
    reference["FRAC"] = [f"{i // 100:02d}" for i in numbers]
    reference["RADIO"] = [f"{i % 100:02d}" for i in numbers]
    reference.to_file(processed / "fictional_reference.geojson", driver="GeoJSON")
    territorial = {"area": {"province_code": "46", "province_name": "LA RIOJA", "department_code": "014", "department_name": "Capital"},
                   "crs": {"source": "EPSG:4326"}, "sources": {"cartography": {
                       "path": "data/processed/fictional_reference.geojson", "encoding": "UTF-8", "columns": {
                           "radio_id": "LINK", "province_code": "PROV", "province_name": "NOMPROV",
                           "department_code": "DEPTO", "department_name": "NOMDEPTO", "fraction": "FRAC", "radio": "RADIO"}}}}
    configs = tmp_path / "ml/configs"
    configs.mkdir(parents=True)
    (configs / "territorial_master.json").write_text(json.dumps(territorial), encoding="utf-8")
    return tmp_path, config, registry, source_path


def test_full_private_pipeline_is_reproducible_and_preserves_sources(fictional_delivery):
    repo_root, config, registry, source = fictional_delivery
    options = dict(SPATIAL_DEFAULTS)
    output = private_output_directory(options, repo_root)
    before = protected_snapshot(repo_root, output)
    report = run_spatial_diagnostics(config, registry, options, repo_root)
    assert report["cartography"]["radio_count"] == 263
    assert report["cartography"]["original_geometry_match"]
    assert report["protected_inputs_and_scientific_artifacts_unchanged"]
    require_preserved(before, protected_snapshot(repo_root, output))
    hashes = {path.name: digest_path(path) for path in output.iterdir()}
    assignments = pd.read_parquet(output / "assignments.parquet")
    assert len(assignments) == 3 and assignments.eligibility.eq("unresolved").all()
    assert assignments.assignment_state.tolist() == ["uncertain", "ambiguous", "unassigned"]
    assert "latitude_candidate" not in assignments and "classification_label" not in assignments
    assert "FICTIONAL_PRIVATE_PERSON" not in (output / "geographic_quality.json").read_text(encoding="utf-8")
    assert "FICTIONAL_PRIVATE_PERSON" not in (output / "territorial_viability.md").read_text(encoding="utf-8")
    run_spatial_diagnostics(config, registry, options, repo_root)
    assert hashes == {path.name: digest_path(path) for path in output.iterdir()}
    assert digest_path(source) == before[str(source.relative_to(repo_root))]


def test_changed_source_is_rejected_before_normalized_read(fictional_delivery, monkeypatch):
    repo_root, config, registry, source = fictional_delivery
    source.write_bytes(source.read_bytes() + b"fictional_changed_source")
    def forbidden(*args, **kwargs):
        pytest.fail("No debe leer normalizados de una fuente cambiada")
    monkeypatch.setattr(pd, "read_parquet", forbidden)
    with pytest.raises(ValueError, match="vigente"):
        read_authorized_normalized(config, registry, repo_root)


def test_disabled_authorization_never_reads_normalized(fictional_delivery, monkeypatch):
    from dataclasses import replace
    from sigard_ml.official.access import AccessDenied, SourceRegistry
    repo_root, config, registry, _ = fictional_delivery
    denied = SourceRegistry((replace(registry.sources[0], enabled=False),))
    def forbidden(*args, **kwargs):
        pytest.fail("No debe leer normalizados sin autorización")
    monkeypatch.setattr(pd, "read_parquet", forbidden)
    with pytest.raises(AccessDenied):
        read_authorized_normalized(config, denied, repo_root)
    def forbidden_snapshot(*args, **kwargs):
        pytest.fail("No debe calcular huellas de fuentes antes de comprobar autorización")
    monkeypatch.setattr("sigard_ml.official.spatial_pipeline.protected_snapshot", forbidden_snapshot)
    with pytest.raises(AccessDenied):
        run_spatial_diagnostics(config, denied, dict(SPATIAL_DEFAULTS), repo_root)
