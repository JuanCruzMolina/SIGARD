from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from sigard_ml.ingestion.territorial import (
    add_spatial_metrics,
    build_radio_id,
    load_census_count,
)


def test_build_radio_id_uses_all_normalized_components() -> None:
    assert build_radio_id(
        pd.Series(["46"]),
        pd.Series(["014"]),
        pd.Series(["01"]),
        pd.Series(["02"]),
    ).tolist() == ["460140102"]


def test_load_census_count_aggregates_exhaustive_categories(tmp_path: Path) -> None:
    source = tmp_path / "persona.csv"
    pd.DataFrame(
        {
            "codigo": ["460140101", "460140101"],
            "cod_prov": ["46", "46"],
            "provincia": ["La Rioja", "La Rioja"],
            "cod_dep": ["014", "014"],
            "departamento": ["014", "014"],
            "fraccion": ["01", "01"],
            "radio": ["01", "01"],
            "cod_variable": ["PERSONA_P02", "PERSONA_P02"],
            "cod_categoria": ["1", "2"],
            "categoria": ["Mujer", "Varón"],
            "cantidad": ["10", "12"],
        }
    ).to_csv(source, index=False, encoding="utf-8-sig")
    config = {
        "area": {"province_code": "46", "department_code": "014"},
        "sources": {
            "population": {
                "path": str(source),
                "encoding": "utf-8-sig",
                "variable": "PERSONA_P02",
                "output_column": "poblacion",
            }
        },
        "census_columns": {
            "radio_id": "codigo",
            "province_code": "cod_prov",
            "province_name": "provincia",
            "department_code": "cod_dep",
            "department_value": "departamento",
            "fraction": "fraccion",
            "radio": "radio",
            "variable": "cod_variable",
            "category_code": "cod_categoria",
            "category": "categoria",
            "count": "cantidad",
        },
    }
    quality = {"input_checks": {}}
    result = load_census_count("population", config, Path("/"), quality)
    assert result.to_dict("records") == [
        {"radio_id": "460140101", "poblacion": 22}
    ]
    assert quality["input_checks"]["population"]["invalid_count_rows"] == 0


def test_add_spatial_metrics_calculates_centroids_and_sorted_neighbors() -> None:
    frame = gpd.GeoDataFrame(
        {"radio_id": ["460140102", "460140101", "460140103"]},
        geometry=[
            box(-66.80, -29.42, -66.79, -29.41),
            box(-66.81, -29.42, -66.80, -29.41),
            box(-66.79, -29.42, -66.78, -29.41),
        ],
        crs="EPSG:4326",
    )
    result = add_spatial_metrics(frame, "EPSG:32719", "EPSG:4326")
    by_id = result.set_index("radio_id")
    assert by_id.loc["460140102", "neighbor_ids"] == ["460140101", "460140103"]
    assert by_id.loc["460140101", "neighbor_ids"] == ["460140102"]
    assert by_id.loc["460140103", "neighbor_ids"] == ["460140102"]
    assert (result["superficie_km2"] > 0).all()
    assert result["centroid_lat"].between(-29.43, -29.40).all()
    assert result["centroid_lon"].between(-66.82, -66.77).all()


def test_add_spatial_metrics_rejects_invalid_geometry() -> None:
    invalid_bowtie = gpd.GeoSeries.from_wkt(
        ["POLYGON ((0 0, 1 1, 1 0, 0 1, 0 0))"], crs="EPSG:4326"
    )
    frame = gpd.GeoDataFrame({"radio_id": ["460140101"]}, geometry=invalid_bowtie)
    with pytest.raises(ValueError, match="Geometrías inválidas"):
        add_spatial_metrics(frame, "EPSG:32719", "EPSG:4326")
