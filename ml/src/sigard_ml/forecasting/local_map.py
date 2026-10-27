"""Representación privada de la consulta existente; sin modelos ni entrenamiento.

Genera un archivo local autocontenido. No sirve rutas HTTP, publica ni cambia
artefactos V1/V2. Reutiliza Leaflet/TerritorialMap compilados sin datos reales.
"""

from datetime import date
import hashlib
import json
from pathlib import Path

from sigard_ml.forecasting.contracts import require
from sigard_ml.forecasting.local_query import query_predictions

SCHEMA = "sigard-private-predictive-viewer/1"


def _verified_json(directory, filename, manifest):
    path = directory / filename
    require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest["outputs_sha256"][filename], "Integridad del informe inválida")
    return json.loads(path.read_text(encoding="utf-8"))


def comparison_records(root):
    """Copia sólo las métricas ya calculadas, sin volver a evaluar ni seleccionar."""
    artifacts = root / "ml/artifacts/official"
    v1, v2 = [artifacts / name for name in ("sigard-principal-v1-experimental", "sigard-principal-v2-experimental")]
    m1, m2 = [json.loads((directory / "manifest.private.json").read_text(encoding="utf-8")) for directory in (v1, v2)]
    old = _verified_json(v1, "metrics.private.json", m1)["test"]["model"]["territorial"]
    candidate = _verified_json(v2, "conditional_empty_feature_repair/metrics.private.json", m2)["comparison_previously_observed"]
    territorial = _verified_json(v2, "count_metrics.private.json", m2)["1"]["comparison_previously_observed"]["lag_1_or_training_mean"]
    return [dict(id=identifier, label=label, scope=scope, **{key: values[key] for key in ("n", "mae", "rmse", "mean_bias")})
        for identifier, label, scope, values in (
            ("V1", "V1 · ML Poisson conservado", "Condicional a celdas positivas; período ya observado", old),
            ("GLM_V2", "GLM V2 · no promovido", "Mismas celdas positivas; período ya observado", candidate),
            ("territorial", "Persistencia / media histórica · utilizado", "Grilla snapshot t+1; sólo etiquetas utilizables", territorial))]


def build_map_payload(frame, geometry, comparison, *, initial_date=None, initial_horizon=1):
    require(geometry.get("type") == "FeatureCollection" and len(geometry.get("features", [])) == 256, "Cartografía territorial incompleta")
    ids = [feature["properties"]["radio_id"] for feature in geometry["features"]]
    require(len(set(ids)) == 256 and set(ids) == set(frame.radio_id), "Predicciones y geometría no coinciden")
    queries = {}
    for horizon, group in frame.groupby("horizon_weeks"):
        entries = []
        for target in sorted(group.target_week.unique()):
            result = query_predictions(frame, target_date=target, horizon_weeks=int(horizon))
            require(result["status"] == "available_private_retrospective_snapshot", "Consulta no admisible en el mapa")
            require(result["selected_method"] == "lag_1_or_training_mean", "La demostración sólo utiliza la referencia territorial seleccionada")
            # No numeric presence scores/probabilities enter this interface.
            for row in result["radios"]:
                for field in ("experimental_presence_score", "presence_output_kind", "presence_quality"):
                    row.pop(field, None)
            entries.append(result)
        queries[str(horizon)] = entries
    require(str(initial_horizon) in queries, "Horizonte sin estimaciones")
    initial_date = initial_date or queries[str(initial_horizon)][0]["target_week"]
    if isinstance(initial_date, date):
        initial_date = initial_date.isoformat()
    return dict(schema=SCHEMA, geometry=geometry, comparison=comparison, queries=queries,
                initial_date=initial_date, initial_horizon=initial_horizon,
                probability_available=False, alerts_enabled=False)


def export_private_map(frame, output, *, initial_date=None, initial_horizon=1):
    root = Path(__file__).resolve().parents[4]
    output = Path(output).resolve()
    require(output.suffix == ".html" and output.name.endswith(".private.html")
            and output.is_relative_to(root / "data/interim/official"), "El mapa debe ser un .private.html bajo data/interim/official")
    require(not output.exists(), "No sobrescribir una representación privada existente")
    template = root / "frontend/.tmp/predictive-viewer/viewer.html"
    require(template.is_file(), "Primero ejecute npm.cmd --prefix frontend run build:predictive-viewer")
    source = template.read_text(encoding="utf-8")
    require(source.count("__SIGARD_PRIVATE_PAYLOAD__") == 1 and "connect-src 'none'" in source, "Plantilla local no válida")
    territory = root / "data/processed/principal_territory_46014010_256_v1"
    manifest = json.loads((territory / "manifest.json").read_text(encoding="utf-8"))
    geometry_path = territory / "territory.parquet"
    require(hashlib.sha256(geometry_path.read_bytes()).hexdigest() == manifest["outputs_sha256"]["territory.parquet"], "Integridad de cartografía inválida")
    import geopandas as gpd
    from pyproj import network
    network.set_network_enabled(False)
    layer = gpd.read_parquet(geometry_path, columns=["radio_id", "geometry"])
    require(layer.crs is not None, "Cartografía sin CRS explícito")
    geometry = json.loads(layer.to_crs(4326).to_json(drop_id=True))
    payload = build_map_payload(frame, geometry, comparison_records(root), initial_date=initial_date, initial_horizon=initial_horizon)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    html = source.replace("__SIGARD_PRIVATE_PAYLOAD__", encoded)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(html)
    return dict(path=str(output), radios=256, query_count=sum(map(len, payload["queries"].values())),
                geometry_sha256=hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
                artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
