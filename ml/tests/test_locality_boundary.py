"""Polígonos inventados; no abre cartografía, SISA ni modelos reales."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box, Polygon

from sigard_ml.official.cartography import compare_locality_boundary


def layers():
    # UTM 19S, tres polígonos artificiales con áreas exactamente conocidas.
    radios = gpd.GeoDataFrame({"radio_id": ["460140001", "460140002", "460140003"]},
        geometry=[box(700000, 6700000, 700100, 6700100),
                  box(700100, 6700000, 700200, 6700100),
                  box(700200, 6700000, 700300, 6700100)], crs=32719)
    locality = gpd.GeoDataFrame(geometry=[box(700000, 6700000, 700150, 6700100)], crs=32719)
    return radios, locality


def test_exact_coverage_partial_area_and_exterior_without_changing_inputs():
    radios, locality = layers()
    before_radios, before_locality = radios.copy(), locality.copy()
    result, report = compare_locality_boundary(radios, locality, expected_count=3)
    assert result.relation.tolist() == ["inside", "partial", "outside"]
    assert result.intersection_fraction.tolist() == [1., .5, 0.]
    assert result.intersection_area_m2.tolist() == [10000., 5000., 0.]
    assert result.outside_area_m2.tolist() == [0., 5000., 10000.]
    assert report["counts"] == dict(inside=1, partial=1, outside=1)
    assert report["locality_area_m2"] == 15000.
    assert report["locality_outside_radio_union_m2"] == 0.
    assert not report["geometry_modified"] and not report["population_or_cases_allocated"]
    assert "geometry" not in result and "population" not in result
    pd.testing.assert_frame_equal(radios, before_radios)
    pd.testing.assert_frame_equal(locality, before_locality)


def test_touching_alone_does_not_select_and_small_positive_area_is_retained():
    radios, locality = layers()
    locality.geometry = [box(700000, 6700000, 700100, 6700100)]
    result, _ = compare_locality_boundary(radios, locality, expected_count=3)
    assert result.relation.tolist() == ["inside", "outside", "outside"]
    assert result.boundary_only_contact.tolist() == [False, True, False]
    locality.geometry = [box(700000, 6700000, 700100.000001, 6700100)]
    result, _ = compare_locality_boundary(radios, locality, expected_count=3)
    assert result.relation.tolist() == ["inside", "partial", "outside"]
    assert 0 < result.iloc[1].intersection_fraction < 1e-7


@pytest.mark.parametrize("failure", ["missing_crs", "empty", "multiple", "invalid", "null", "wrong_type", "no_geometry", "not_geodataframe"])
def test_boundary_requires_explicit_single_valid_polygon(failure):
    radios, locality = layers()
    if failure == "missing_crs": locality = locality.set_crs(None, allow_override=True)
    elif failure == "empty": locality = locality.iloc[:0]
    elif failure == "multiple": locality = pd.concat([locality, locality])
    elif failure == "invalid": locality.geometry = [Polygon([(700000, 6700000), (700100, 6700100), (700000, 6700100), (700100, 6700000)])]
    elif failure == "null": locality.geometry = [None]
    elif failure == "wrong_type": locality.geometry = locality.geometry.centroid
    elif failure == "no_geometry": locality = gpd.GeoDataFrame({"name": ["fictional"]})
    elif failure == "not_geodataframe": locality = pd.DataFrame({"name": ["fictional"]})
    with pytest.raises(ValueError, match="localidad"):
        compare_locality_boundary(radios, locality, expected_count=3)


def test_order_and_crs_conversion_preserve_rules():
    radios, locality = layers()
    baseline, _ = compare_locality_boundary(radios, locality, expected_count=3)
    reordered, _ = compare_locality_boundary(radios.iloc[::-1], locality, expected_count=3)
    pd.testing.assert_frame_equal(baseline, reordered)
    converted, _ = compare_locality_boundary(radios, locality.to_crs(4326), expected_count=3)
    # Una reproyección introduce diferencias de redondeo en los bordes: se
    # conservan proporciones, sin reinterpretar contactos con un buffer.
    assert converted.intersection_fraction.sub(baseline.intersection_fraction).abs().max() < 1e-8
    assert converted.iloc[1].relation == "partial"


def test_locality_outside_master_is_reported_without_clipping():
    radios, locality = layers()
    locality.geometry = [box(700000, 6700000, 700350, 6700100)]
    result, report = compare_locality_boundary(radios, locality, expected_count=3)
    assert result.relation.eq("inside").all()
    assert report["locality_area_m2"] == 35000.
    assert report["locality_outside_radio_union_m2"] == 5000.
    assert not report["geometry_modified"]
