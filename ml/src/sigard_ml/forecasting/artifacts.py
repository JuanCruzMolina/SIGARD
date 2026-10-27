"""Persistencia privada explícita de una ejecución; nunca carga ni publica modelos."""

import hashlib
import json
from pathlib import Path

import joblib

from sigard_ml.forecasting.contracts import require
from sigard_ml.forecasting.dataset import FEATURES


def save_experiment(result, destination, *, configuration, provenance):
    """Guarda una versión nueva bajo ml/artifacts/official, sin sobrescritura.

    configuration y provenance deben ser JSON sin registros individuales. Sólo
    serializa el resultado ya ajustado: no vuelve a entrenar ni a predecir.
    joblib es un formato privado de confianza local; no leer archivos no confiables.
    """
    root = Path(__file__).resolve().parents[4]
    destination = Path(destination).resolve()
    private_root = root / "ml/artifacts/official"
    require(destination.is_relative_to(private_root) and destination != private_root,
            "Los artefactos deben guardarse en una versión privada del modelo")
    require(not destination.exists(), "No sobrescribir una versión existente")
    require(isinstance(configuration.get("artifact_version"), str)
            and bool(configuration["artifact_version"].strip()), "Falta versión del artefacto")
    # Validar metadatos antes de crear el destino.
    payloads = {
        "configuration.private.json": configuration,
        "provenance.private.json": provenance,
        "metrics.private.json": result.report,
        "features.private.json": {"ordered_features": list(FEATURES),
                                  "fitted_parameters": str(result.fitted.model.get_params())},
    }
    encoded = {name: json.dumps(value, ensure_ascii=False, sort_keys=True,
                               indent=2, allow_nan=False) + "\n" for name, value in payloads.items()}
    require(not result.evaluation_predictions.empty, "Faltan predicciones de evaluación")
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in encoded.items():
        (destination / name).write_text(content, encoding="utf-8")
    joblib.dump(result.fitted, destination / "model.private.joblib")
    result.evaluation_predictions.to_parquet(destination / "evaluation_predictions.private.parquet", index=False)
    columns = ["radio_id", "origin_week", "target_week", "target_end", "partition", "target_count", "target_state"]
    result.panel[columns].to_parquet(destination / "temporal_split.private.parquet", index=False)
    result.panel[[*columns, *FEATURES]].to_parquet(destination / "modeling_panel.private.parquet", index=False)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(destination.iterdir())}
    manifest = {"model_id": result.fitted.model_id, "artifact_version": configuration["artifact_version"],
                "private_local_only": True, "production_inference_authorized": False,
                "outputs_sha256": hashes}
    (destination / "manifest.private.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest
