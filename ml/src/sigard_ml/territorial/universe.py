"""Versiona unidades censales completas; nunca lee ni asigna pacientes.

Extensión del constructor territorial existente. Reutiliza la comparación ya
revisada y el validador geométrico/vecinal; no repite la auditoría de localidad.
"""

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from sigard_ml.official.cartography import validate_metric_extent, validate_radios
from sigard_ml.official.spatial_ml.dataset import territorial_context


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _path(root, value, folders):
    root = Path(root).resolve()
    path = (root / value).resolve()
    _require(any(path.is_relative_to(root / "data" / folder) for folder in folders),
             "Ruta territorial fuera del directorio permitido")
    return path


def validate_context(frame, expected_count):
    """IDs, población, densidad, área métrica, geometría y grafo queen completo."""
    validate_metric_extent(frame)
    return territorial_context(frame, expected_count=expected_count)


def graph_edges(frame):
    return tuple(sorted((row.radio_id, str(other))
                        for row in frame.itertuples() for other in row.neighbor_ids))


def build_universe(master, comparison, config):
    """Selecciona sin recortes, ponderaciones ni mutaciones de las entradas."""
    expected = config["expected_counts"]
    _require(config["decision"]["status"] == "approved_operational_scope"
             and config["decision"]["epidemiological_eligibility"] is False
             and config["decision"]["historical_availability_accredited"] is False,
             "Falta decisión operativa separada de elegibilidad epidemiológica")
    _require(config["minimum_inside_fraction"] == 0.9999, "Umbral operativo incompatible")
    validate_radios(master, expected_count=expected["source"])
    required = {"radio_id", "locality_code", "relation", "intersection_fraction_raw",
                "radio_area_m2", "intersection_area_m2", "outside_area_m2",
                "metric_crs", "transformation_version"}
    _require(required <= set(comparison.columns), "Comparación incompleta")
    _require(len(comparison) == len(master) and comparison.radio_id.is_unique
             and set(comparison.radio_id) == set(master.radio_id), "IDs de comparación incompatibles")
    _require(comparison.locality_code.eq(config["locality_code"]).all()
             and comparison.metric_crs.eq("EPSG:32719").all()
             and comparison.transformation_version.eq("locality-radio-comparison-1").all(),
             "Localidad o versión de comparación incompatible")
    _require(comparison.relation.isin(["inside", "partial", "outside"]).all(), "Relación inválida")
    numeric = comparison[["intersection_fraction_raw", "radio_area_m2",
                          "intersection_area_m2", "outside_area_m2"]]
    _require(all(pd.api.types.is_numeric_dtype(numeric[c]) and not pd.api.types.is_bool_dtype(numeric[c])
                 for c in numeric), "Comparación debe ser numérica")
    _require(np.isfinite(numeric.to_numpy()).all() and numeric.ge(0).all().all()
             and comparison.radio_area_m2.gt(0).all()
             and comparison.intersection_fraction_raw.le(1 + 1e-12).all(), "Áreas/fracciones inválidas")
    inside = comparison.relation.eq("inside")
    partial = comparison.relation.eq("partial")
    outside = comparison.relation.eq("outside")
    fraction = comparison.intersection_fraction_raw
    _require(np.allclose(fraction[inside], 1, rtol=0, atol=1e-12)
             and fraction[partial].gt(0).all() and fraction[partial].lt(1).all()
             and fraction[outside].eq(0).all(), "Relación y fracción inconsistentes")
    indexed = master.set_index("radio_id")
    _require(np.allclose(comparison.radio_area_m2,
                        indexed.loc[comparison.radio_id].to_crs(32719).area, rtol=1e-6)
             and np.allclose(fraction, comparison.intersection_area_m2 / comparison.radio_area_m2,
                             rtol=1e-12, atol=1e-15)
             and np.allclose(comparison.radio_area_m2,
                             comparison.intersection_area_m2 + comparison.outside_area_m2, rtol=1e-9),
             "Comparación ajena a las superficies del maestro")
    near = partial & fraction.ge(config["minimum_inside_fraction"])
    selected = set(comparison.loc[inside | near, "radio_id"])
    counts = dict(source=len(master), inside=int(inside.sum()), near_complete=int(near.sum()),
                  selected=len(selected), excluded=len(master) - len(selected))
    _require(counts == expected, "Cantidad seleccionada distinta de la decisión aprobada")
    # Valida el grafo original antes de inducirlo: no ocultar referencias corruptas.
    original_edges = graph_edges(master)
    _require(len(original_edges) == len(set(original_edges)), "Aristas originales duplicadas")
    edge_set, source_ids = set(original_edges), set(master.radio_id)
    _require(all(a != b and b in source_ids and (b, a) in edge_set for a, b in edge_set),
             "Grafo original inválido")
    result = master.loc[master.radio_id.isin(selected)].sort_values("radio_id").copy().reset_index(drop=True)
    result["neighbor_ids"] = result.neighbor_ids.map(lambda values: sorted(set(values) & selected))
    validate_context(result, expected["selected"])
    edges = graph_edges(result)
    neighbors = dict(zip(result.radio_id, result.neighbor_ids))
    remaining, components = set(selected), 0
    while remaining:
        components += 1
        pending = [remaining.pop()]
        while pending:
            for other in set(neighbors[pending.pop()]) & remaining:
                remaining.remove(other)
                pending.append(other)
    report = dict(counts=counts, selected_ids=sorted(selected), excluded_ids=sorted(source_ids - selected),
                  population_total=int(result.poblacion.sum()), area_km2_total=float(result.superficie_km2.sum()),
                  directed_edges=len(edges), graph_components=components,
                  isolated_radios=sum(not values for values in result.neighbor_ids),
                  excluded_neighbor_references_removed=sum(a in selected and b not in selected for a, b in original_edges),
                  closed_symmetric_graph=True, attributes_and_whole_geometries_preserved=True,
                  census_reference_year=2022, data_kind="official_census_context",
                  geometry_crs=result.crs.to_string(), metric_crs="EPSG:32719",
                  patient_assignments_modified=False, counts_created=False, training_authorized=False)
    return result, report


def create_version(config, root):
    """Escribe una versión nueva desde dos entradas fijadas por SHA-256."""
    paths = {name: _path(root, item["path"], ("processed", "interim"))
             for name, item in config["inputs"].items()}
    _require(set(paths) == {"master", "comparison"}, "Entradas territoriales incompatibles")
    for name, path in paths.items():
        _require(sha256(path) == config["inputs"][name]["sha256"], "Integridad de entrada territorial inválida")
    master = gpd.read_parquet(paths["master"])
    comparison = pd.read_csv(paths["comparison"], dtype={"radio_id": str, "locality_code": str})
    frame, report = build_universe(master, comparison, config)
    output = _path(root, config["output_directory"], ("processed",))
    _require(not output.exists() and not any(path.is_relative_to(output) for path in paths.values()),
             "No sobrescribir fuentes ni versiones territoriales")
    output.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(output / "territory.parquet", index=False)
    _json(output / "graph.json", dict(territory_version=config["territory_version"],
                                     radios=frame.radio_id.tolist(), edges=graph_edges(frame)))
    # Verificación de exportación con el mismo contrato; no modifica la fuente.
    reopened = gpd.read_parquet(output / "territory.parquet")
    validate_context(reopened, config["expected_counts"]["selected"])
    pd.testing.assert_frame_equal(frame.drop(columns="neighbor_ids"), reopened.drop(columns="neighbor_ids"))
    _require(graph_edges(frame) == graph_edges(reopened), "Grafo alterado durante exportación")
    for name, path in paths.items():
        _require(sha256(path) == config["inputs"][name]["sha256"], "Fuente territorial modificada")
    _json(output / "manifest.json", dict(configuration=config, validation=report,
          outputs_sha256={name: sha256(output / name) for name in ("territory.parquet", "graph.json")}))
    return report


def load_version(config, root):
    """Carga sólo el contexto versionado; nunca descubre fuentes sanitarias."""
    output = _path(root, config["output_directory"], ("processed",))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    _require(manifest["configuration"] == config, "Configuración ajena a la versión territorial")
    _require(set(manifest["outputs_sha256"]) == {"territory.parquet", "graph.json"}, "Manifiesto incompatible")
    for name, expected in manifest["outputs_sha256"].items():
        _require(sha256(output / name) == expected, "Integridad de versión territorial inválida")
    frame = gpd.read_parquet(output / "territory.parquet")
    validate_context(frame, config["expected_counts"]["selected"])
    graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    _require(graph == dict(territory_version=config["territory_version"], radios=frame.radio_id.tolist(),
                           edges=[list(edge) for edge in graph_edges(frame)]), "Grafo y territorio incompatibles")
    return frame
