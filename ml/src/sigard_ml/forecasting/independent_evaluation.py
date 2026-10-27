"""Two-command, local evaluation of frozen V3 on authorized prepared aggregates.

seal reads ONLY features and their permission. score subsequently reads labels.
No fit method, source discovery, raw ingestion, production promotion or training
entrypoint exists here. Custodian declarations are a human trust boundary; hashes
prove file integrity, never authorization authenticity or historical non-exposure.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from sigard_ml.forecasting.contracts import require
from sigard_ml.forecasting.evaluation import count_metrics
from sigard_ml.forecasting.thesis_validation import (
    DEFAULT_ARTIFACT, ROOT, METHODS, FrozenArtifact, compare, digest, paired_frame,
    read_json, write_json,
)
from sigard_ml.forecasting.v3 import BASELINES, CANDIDATES, FEATURES, VERSION

SCHEMA = "sigard-v3-independent-panel-1"
TERRITORY = "la-rioja-46014010-256-v1"
FEATURE_RULE = "frozen-v3-origin-closed-1"
DEFINITION = "principal-confirmed-snapshot-2"


def iso(value):
    require(isinstance(value, str), "Fecha ISO requerida")
    result = date.fromisoformat(value)
    require(result.isoformat() == value, "Fecha ISO no canónica")
    return result


def private_path(path):
    resolved = Path(path).resolve()
    require(any(resolved.is_relative_to(ROOT / "data" / folder) for folder in ("interim", "processed")),
            "Entradas/salidas sólo en data/interim o data/processed privados")
    return resolved


def permission(path, payload, *, purpose):
    """Permission is checked before interpreting a data payload."""
    record = read_json(path)
    require(record.get("status") == "approved" and record.get("purpose") == purpose,
            "Falta permiso específico de evaluación independiente")
    require(record.get("payload_sha256") == digest(payload), "Permiso ajeno al paquete")
    require(record.get("authorization_basis") in ("project_owner_declared_provision", "external_provider_permission"),
            "Fundamento de autorización ausente")
    require(all(isinstance(record.get(k), str) and record[k].strip()
                for k in ("reviewer_ref", "authorization_ref", "source_version", "limits")), "Permiso incompleto")
    require(record.get("training_embargo") is True and record.get("previously_used_or_reviewed") is False
            and record.get("local_only") is True, "Sin embargo o con exposición previa")
    require(iso(record["decided_on"]) <= date.today(), "Permiso aún no vigente")
    return record


def validate_panel(payload, *, radios, last_seen):
    require(payload.get("schema") == SCHEMA and payload.get("territory_version") == TERRITORY
            and payload.get("unit") == "snapshot_record_count" and payload.get("target_definition") == DEFINITION
            and payload.get("feature_rule") == FEATURE_RULE and payload.get("model_version") == VERSION,
            "Unidad, territorio, transformación u objetivo incompatible")
    require(payload.get("feature_order") == list(FEATURES), "Features incompatibles")
    require(set(payload.get("radios", [])) == set(radios) and len(payload["radios"]) == len(radios),
            "Universo territorial incompatible")
    require(payload.get("zero_meaning") == "no_record_in_filtered_snapshot_not_epidemiological_absence"
            and payload.get("availability_evidence_ref") and payload.get("preparation_review_ref"),
            "Falta semántica de cero, disponibilidad o revisión de preparación")
    rows = payload.get("rows")
    require(isinstance(rows, list) and rows, "Panel vacío")
    frame = pd.DataFrame(rows)
    fields = {"radio_id", "horizon", "origin_week", "target_week", "cutoff_date", "features", "lineage"}
    require(set(frame) == fields and not frame.isna().any().any(), "Columnas de panel incompatibles")
    require(not frame.duplicated(["radio_id", "target_week", "horizon"]).any(), "Panel duplicado")
    require(set(frame.horizon) == {1, 2, 4}, "Se requieren los tres horizontes congelados")
    result = []
    for row in rows:
        origin, target, cutoff = [iso(row[k]) for k in ("origin_week", "target_week", "cutoff_date")]
        require(type(row["horizon"]) is int and origin.weekday() == target.weekday() == 6
                and target - origin == timedelta(weeks=row["horizon"])
                and cutoff == origin + timedelta(days=6) and cutoff <= date.today(), "Fechas/horizonte incompatibles")
        require(target > last_seen and origin > last_seen and target.year != 2022, "Reutilización de período observado")
        values, lineage = row["features"], row["lineage"]
        require(set(values) == set(FEATURES) == set(lineage), "Features o procedencia incompletas")
        for name, value in values.items():
            evidence = lineage[name]
            if value is None:
                require(evidence is None, "Feature ausente con procedencia contradictoria")
                continue
            require(type(value) in (int, float) and np.isfinite(value), "Feature no finita/no numérica")
            require(isinstance(evidence, dict) and set(evidence) == {"max_event_week", "available_on", "source_ref"}
                    and isinstance(evidence["source_ref"], str) and evidence["source_ref"], "Procedencia de feature ausente")
            event, available = iso(evidence["max_event_week"]), iso(evidence["available_on"])
            require(event.weekday() == 6 and event <= origin and event <= available <= cutoff,
                    "Feature futura o disponibilidad posterior al corte")
            if name not in ("population", "population_density", "season_sin", "season_cos"):
                require(event + timedelta(days=6) <= available, "Agregado disponible antes del cierre")
            if name.startswith("cases_lag_"):
                require(event <= origin - timedelta(weeks=int(name.rsplit("_", 1)[1])), "Rezago mal fechado")
            if name not in ("recent_trend", "season_sin", "season_cos", "temperature_origin", "temperature_mean_4_origin"):
                require(value >= 0, "Feature no negativa fuera de rango")
            if name in ("season_sin", "season_cos"):
                require(abs(value) <= 1, "Estacionalidad fuera de rango")
            if name == "humidity_origin":
                require(value <= 100, "Humedad fuera de rango")
            if name == "neighbor_known_fraction":
                require(value <= 1, "Fracción vecinal fuera de rango")
        result.append(dict(radio_id=row["radio_id"], horizon=row["horizon"], origin_week=origin,
                           target_week=target, cutoff_date=cutoff, **values))
    result = pd.DataFrame(result)
    for _, group in result.groupby(["horizon", "origin_week"]):
        require(set(group.radio_id) == set(radios) and len(group) == len(radios), "Grilla territorial incompleta")
    return result.sort_values(["horizon", "target_week", "radio_id"]).reset_index(drop=True)


def seal(features, authorization, output, artifact_directory=DEFAULT_ARTIFACT):
    features, authorization, output = map(private_path, (features, authorization, output))
    require(not output.exists(), "No sobrescribir evaluación sellada")
    authorization_sha = digest(authorization)
    permit = permission(authorization, features, purpose="independent_features")
    payload = read_json(features)
    require(digest(features) == permit["payload_sha256"], "Entrada cambió después de autorizar")
    require(payload.get("source_version") == permit["source_version"], "Versión fuera del permiso")
    artifact = FrozenArtifact(artifact_directory)
    config = artifact.json("configuration.private.json")
    current_versions = dict(sklearn=sklearn.__version__, numpy=np.__version__,
                            pandas=pd.__version__, joblib=joblib.__version__)
    require(all(config["versions"].get(k) == v for k, v in current_versions.items()), "Entorno ML incompatible")
    # Pickles are never accepted from the incoming data package.
    require(Path(artifact_directory).resolve() == DEFAULT_ARTIFACT.resolve(), "Sólo artefacto V3 local de confianza")
    for name in ("v3.py", "v2.py", "contracts.py"):
        require(digest(Path(__file__).with_name(name)) == digest(artifact.path(f"implementation/{name}")),
                "Implementación V3 modificada")
    provenance = artifact.json("provenance.private.json")
    seen = max(provenance["source_input_evidence"]["snapshot_scenario"]["covered_weeks"])
    panel = artifact.frame("horizon_1/modeling_panel.private.parquet")
    last_seen = max([iso(seen), *[max(artifact.frame(f"horizon_{h}/modeling_panel.private.parquet").target_week)
                                for h in (1, 2, 4)]])
    frame = validate_panel(payload, radios=panel.radio_id.unique(), last_seen=last_seen)
    selection = artifact.json("selection.private.json")
    outputs = []
    thresholds = {}
    for h, group in frame.groupby("horizon", sort=True):
        models = joblib.load(artifact.path(f"horizon_{h}/models.private.joblib"))["counts"]
        predicted = group[["radio_id", "horizon", "origin_week", "target_week", "cutoff_date"]].copy()
        for name in METHODS:
            model = models[name]
            require(model.horizon_weeks == h and model.fit_cutoff < min(group.origin_week), "Modelo posterior al origen")
            predicted[name] = model.predict_frame(group)
            require(np.isfinite(predicted[name]).all() and predicted[name].ge(0).all(), "Predicción inválida")
        historical = artifact.frame(f"horizon_{h}/modeling_panel.private.parquet")
        dev = historical.loc[historical.partition.isin(["train", "validation"])
                             & historical.predictor_admissible & historical.target_count.notna()]
        thresholds[str(h)] = dict(high_week=float(dev.groupby("target_week").target_count.sum().quantile(.8)),
                                  high_count=max(2., float(dev.target_count.quantile(.9))))
        outputs.append(predicted)
    artifact.unchanged()
    require(digest(features) == permit["payload_sha256"] and digest(authorization) == authorization_sha,
            "Entrada o permiso cambió durante la inferencia")
    output.mkdir(parents=True)
    pd.concat(outputs, ignore_index=True).to_parquet(output / "predictions.private.parquet", index=False)
    receipt = dict(schema=SCHEMA, model_version=VERSION, training_embargo=True, phase="sealed_without_labels",
                   sealed_at=datetime.now(timezone.utc).isoformat(), source_version=permit["source_version"],
                   feature_sha256=permit["payload_sha256"], authorization_sha256=authorization_sha,
                   predictions_sha256=digest(output / "predictions.private.parquet"),
                   artifact_sha256=artifact.inputs, selection=selection["horizons"], thresholds=thresholds,
                   implementation_sha256=digest(Path(__file__)),
                   seen_through=last_seen.isoformat(), heldout_attestation=permit,
                   independence="custodian_declared_unseen_requires_human_verification")
    write_json(output / "seal.private.json", receipt)
    return receipt


def score(labels, authorization, sealed):
    labels, authorization, sealed = map(private_path, (labels, authorization, sealed))
    require(not (sealed / "evaluation.private.json").exists(), "Evaluación ya terminada; no repetir para seleccionar")
    receipt = read_json(sealed / "seal.private.json")
    require(receipt["schema"] == SCHEMA and receipt["phase"] == "sealed_without_labels"
            and receipt["training_embargo"] is True, "Sello inválido")
    require(receipt["implementation_sha256"] == digest(Path(__file__)), "Evaluador cambió después del sello")
    require(receipt["predictions_sha256"] == digest(sealed / "predictions.private.parquet"), "Predicciones alteradas")
    authorization_sha = digest(authorization)
    permit = permission(authorization, labels, purpose="independent_labels")
    payload = read_json(labels)
    require(digest(labels) == permit["payload_sha256"], "Etiquetas cambiaron después de autorizar")
    require(payload.get("schema") == SCHEMA and payload.get("unit") == "snapshot_record_count"
            and payload.get("target_definition") == DEFINITION and payload.get("territory_version") == TERRITORY,
            "Etiquetas incompatibles")
    require(payload.get("seal_sha256") == digest(sealed / "seal.private.json"), "Etiquetas ajenas al sello")
    require(payload.get("source_version") == permit["source_version"], "Versión de etiquetas no autorizada")
    label_frame = pd.DataFrame(payload["rows"])
    require(set(label_frame) == {"radio_id", "target_week", "target_count", "state", "available_on", "source_ref"}
            and len(label_frame) > 0, "Esquema de etiquetas incompatible")
    label_frame["target_week"] = label_frame.target_week.map(iso)
    require(not label_frame.duplicated(["radio_id", "target_week"]).any(), "Etiquetas duplicadas")
    for row in label_frame.itertuples():
        require(row.source_ref and row.state in ("usable_snapshot", "unknown", "pending", "temporal_problem"), "Estado/procedencia inválidos")
        require(row.target_week > iso(receipt["seen_through"]), "Etiqueta ya observada")
        if row.state == "usable_snapshot":
            require(pd.notna(row.target_count) and type(row.target_count) in (int, float)
                    and np.isfinite(row.target_count) and row.target_count >= 0 and row.target_count == int(row.target_count),
                    "Conteo utilizable inválido")
            require(row.target_week + timedelta(days=6) <= iso(row.available_on) <= date.today(), "Etiqueta anterior al cierre o futura")
        else:
            require(pd.isna(row.target_count), "Desconocido/pendiente debe conservar null")
    predictions = pd.read_parquet(sealed / "predictions.private.parquet")
    keys = set(predictions[["radio_id", "target_week"]].itertuples(index=False, name=None))
    require(keys == set(label_frame[["radio_id", "target_week"]].itertuples(index=False, name=None)),
            "Etiquetas deben incluir exactamente toda la grilla, con null explícito")
    paired = predictions.merge(label_frame, on=["radio_id", "target_week"], validate="many_to_one")
    report = dict(independence=receipt["independence"], training_embargo=True, retrained=False,
                  labels_sha256=permit["payload_sha256"], authorization_sha256=authorization_sha,
                  seal_sha256=digest(sealed / "seal.private.json"), horizons={})
    markdown = ["# Evaluación privada de V3 congelada", "",
                "Independencia declarada por el custodio: requiere verificación humana. Sin reentrenamiento.", ""]
    for h, all_rows in paired.groupby("horizon", sort=True):
        frame = paired_frame(all_rows, h)
        require(frame.target_week.nunique() >= 4, "Menos de cuatro semanas utilizables; no concluir superioridad")
        rows = [compare(frame, name, baseline, high_threshold=receipt["thresholds"][str(h)]["high_week"], horizon=h)
                for name in CANDIDATES for baseline in BASELINES[:2]]
        # Same V3 thresholds; prospective stability uses three chronological
        # evaluation blocks, with no adjustment or fitting inside these blocks.
        dates = sorted(frame.target_week.unique())
        blocks = [frame.loc[frame.target_week.isin(part)] for part in np.array_split(np.array(dates, dtype=object), 3)]
        tail = frame.target_count.ge(receipt["thresholds"][str(h)]["high_count"])
        for row in rows:
            name, baseline = row["method"], row["baseline"]
            block_metrics = [dict(ml=count_metrics(part.target_count, part[name]),
                                  persistence=count_metrics(part.target_count, part[baseline])) for part in blocks]
            high_count = (dict(ml=count_metrics(frame.loc[tail,"target_count"], frame.loc[tail,name]),
                               persistence=count_metrics(frame.loc[tail,"target_count"], frame.loc[tail,baseline])) if tail.any() else None)
            row["high_count"] = high_count
            row["chronological_blocks"] = block_metrics
            high_week = row["high_week_total_rmse"]
            gates = dict(mae=row["ml"]["mae"] <= .97*row["persistence"]["mae"],
                         rmse=row["ml"]["rmse"] <= 1.02*row["persistence"]["rmse"],
                         rmse_reduced=row["delta_rmse"] < 0, bias=row["bias_acceptable"],
                         high_count=high_count is not None and high_count["ml"]["mae"] <= 1.05*high_count["persistence"]["mae"],
                         high_week=high_week is not None and high_week["ml"] <= 1.05*high_week["persistence"],
                         stability=sum(b["ml"]["mae"] < b["persistence"]["mae"] for b in block_metrics) >= 2
                         and all(b["ml"]["mae"] <= 1.10*b["persistence"]["mae"] for b in block_metrics),
                         uncertainty=next(b for b in row["bootstrap"] if b["block_weeks"] == 3)["intervals"]["mae"][1] < 0)
            row["gates"] = gates
            row["numeric_criteria_passed"] = all(value for key, value in gates.items() if key != "rmse_reduced")
        candidate = receipt["selection"][str(h)]["best_ml"]
        candidate_passed = all(row["numeric_criteria_passed"] for row in rows if row["method"] == candidate)
        conclusion = ("Mejora preliminar: criterios numéricos cumplidos; confirmar independencia y soporte con revisión humana"
                      if candidate_passed else "Mejora no demostrada según los criterios congelados")
        report["horizons"][str(h)] = dict(comparisons=rows, n=len(frame), weeks=int(frame.target_week.nunique()),
                                          excluded_unknown=len(all_rows) - len(frame),
                                          prespecified_candidate=candidate, conclusion=conclusion)
        markdown += [f"## t+{h}", "", f"{len(frame)} celdas; {frame.target_week.nunique()} semanas; {len(all_rows)-len(frame)} desconocidas excluidas.", "",
                     "| Método | Baseline | MAE ML / persistencia | RMSE ML / persistencia | Sesgo ML / persistencia | Semanas ML / persistencia | IC95 ΔMAE bloques 3 | Sesgo aceptable |",
                     "|---|---|---|---|---|---|---|---|"]
        for row in rows:
            m, b = row["ml"], row["persistence"]
            interval = next(x for x in row["bootstrap"] if x["block_weeks"] == 3)["intervals"]["mae"]
            markdown.append(f"| {row['method']} | {row['baseline']} | {m['mae']:.5f} / {b['mae']:.5f} | {m['rmse']:.5f} / {b['rmse']:.5f} | {m['mean_bias']:.5f} / {b['mean_bias']:.5f} | {row['wins_ml']} / {row['wins_persistence']} | [{interval[0]:.5f}, {interval[1]:.5f}] | {row['bias_acceptable']} |")
        markdown += ["", conclusion, "",
                     "La tabla informa evidencia; no promueve modelos ni autoriza entrenamiento. El JSON adjunto incluye colas, semanas de muchos registros, sensibilidad, bloques cronológicos y cada condición. Falta soporte de colas/semanas altas => criterio no demostrado. Verificar independencia y suficiencia temporal antes de afirmar superioridad.", ""]
    require(digest(labels) == permit["payload_sha256"] and digest(authorization) == authorization_sha
            and digest(sealed / "predictions.private.parquet") == receipt["predictions_sha256"],
            "Entrada cambió durante la evaluación")
    write_json(sealed / "evaluation.private.json", report)
    with (sealed / "report.private.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(markdown))
    # Quarantine remains in force even after scoring; no automated training release.
    write_json(sealed / "completion.private.json", dict(training_embargo=True, evaluation_completed=True,
               human_independence_review_pending=True, report_sha256=digest(sealed / "report.private.md"),
               metrics_sha256=digest(sealed / "evaluation.private.json")))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    forecast = sub.add_parser("seal")
    forecast.add_argument("--features", type=Path, required=True)
    forecast.add_argument("--authorization", type=Path, required=True)
    forecast.add_argument("--output", type=Path, required=True)
    evaluate = sub.add_parser("score")
    evaluate.add_argument("--labels", type=Path, required=True)
    evaluate.add_argument("--authorization", type=Path, required=True)
    evaluate.add_argument("--sealed", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "seal":
        seal(args.features, args.authorization, args.output)
    else:
        score(args.labels, args.authorization, args.sealed)
    print(json.dumps(dict(completed=True, phase=args.command, retrained=False, training_embargo=True)))


if __name__ == "__main__":
    main()
