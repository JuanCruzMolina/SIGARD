"""Consulta privada reproducible por fecha/radio; no carga modelos ejecutables.

Reutiliza el planificador manual. Sólo lee predicciones retrospectivas selladas
de V2 o V3 explícita; fechas sin origen disponible devuelven estado insuficiente.
"""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sigard_ml.forecasting.contracts import ForecastError, require
from sigard_ml.forecasting.prediction import _query_date, resolve_date_query


def query_predictions(frame, *, target_date, horizon_weeks=1, radio_id=None, as_of=None):
    as_of = as_of or date.today()
    target_date = _query_date(target_date)
    require(type(horizon_weeks) is int and horizon_weeks in (1, 2, 4), "Horizonte no soportado")
    base = dict(requested_date=target_date.isoformat(), generated_as_of=as_of.isoformat(),
        horizon_weeks=horizon_weeks, production_inference_authorized=False, retrospective=True,
        probability_status="under_evaluation_not_available_for_alerts", probability_available=False,
        probability_notice="Probabilidad territorial en evaluación; no disponible para alertas.",
        radios=[], expected_territorial_total=None, expected_eligible_total=None,
        eligible_radios=0, radios_without_estimate=256)
    selected = frame.loc[frame.horizon_weeks.eq(horizon_weeks)]
    if selected.empty:
        return dict(base, status="unavailable_horizon", reason="No trained and evaluated artifact for this horizon")
    try:
        plan = resolve_date_query(target_date, as_of=as_of,
            information_cutoff=max(selected.cutoff_date), horizon_weeks=horizon_weeks)
    except ForecastError:
        return dict(base, status="insufficient_origin_data", reason="No admissible epidemiological/climate origin for this date")
    target = date.fromisoformat(plan["target_week"])
    rows = selected.loc[selected.target_week.eq(target)].copy()
    if rows.empty:
        return dict(base, **{k: v for k, v in plan.items() if k not in base},
                    status="insufficient_origin_data", reason="Date outside evaluated snapshot weeks or no pre-origin model/predictors")
    require(len(rows) == 256 and rows.radio_id.nunique() == 256, "Predicciones territoriales incompletas")
    require(rows.origin_week.eq(date.fromisoformat(plan["origin_week"])).all()
            and rows.cutoff_date.eq(date.fromisoformat(plan["information_cutoff"])).all(),
            "Corte u horizonte inconsistente con la fecha consultada")
    require(rows.fit_cutoff.le(rows.cutoff_date).all(), "Modelo ajustado después del origen consultado")
    known = rows.expected_count.notna()
    require(np.isfinite(rows.loc[known, "expected_count"]).all() and rows.loc[known, "expected_count"].ge(0).all(), "Conteos territoriales inválidos")
    require(rows.loc[~known, "predictor_status"].isin(["insufficient_data", "not_available"]).all(), "Conteo ausente sin estado de disponibilidad")
    total = float(rows.loc[known, "expected_count"].sum()) if known.any() else None
    eligible = int(known.sum())
    incomplete = rows.predictor_status.eq("partial_missing_recent_radio_counts")
    incomplete_count = int(incomplete.sum())
    method = rows.selected_method.iloc[0] if "selected_method" in rows else "territorial_reference_unspecified"
    rows["estimate_status"] = np.where(~known, "insufficient_data", np.where(incomplete, "available_with_historical_mean_fallback", "available"))
    if radio_id is not None:
        require(radio_id in set(rows.radio_id), "Radio ajeno al territorio")
        rows = rows.loc[rows.radio_id.eq(radio_id)]
    fields = ["radio_id", "expected_count",
              "predictor_status", "available_features", "missing_features", "quality_warning", "model_version",
              "observed_snapshot_count", "observed_quality_state", "estimate_status"]
    records = []
    for _, row in rows.iterrows():
        item = {field: row[field] for field in fields if field in rows}
        for key, value in item.items():
            if isinstance(value, (list, tuple)) or hasattr(value, "tolist") and getattr(value, "ndim", 0) > 0:
                item[key] = list(value)
            elif pd.isna(value):
                item[key] = None
            elif hasattr(value, "item"):
                item[key] = value.item()
        records.append(item)
    return dict(base, **{k: v for k, v in plan.items() if k not in base}, status="available_private_retrospective_snapshot",
        expected_territorial_total=total if eligible == 256 else None, expected_eligible_total=total,
        eligible_radios=eligible, radios_without_estimate=256-eligible,
        radios_with_incomplete_predictors=incomplete_count, selected_method=method,
        model_version=str(rows.model_version.iloc[0]) if "model_version" in rows else None,
        territory_radios=256, radios=records,
        warning="Snapshot filter scenario; approximate attribution and pending masks. Observations and estimates differ; no epidemiological absence or infection risk claim.")


def _artifact_directory(directory):
    root = Path(__file__).resolve().parents[4]
    directory = Path(directory).resolve()
    require(directory.is_relative_to(root / "ml/artifacts/official")
            and directory.name in ("sigard-principal-v2-experimental", "sigard-principal-v3-experimental"),
            "Sólo artefactos privados V2/V3 locales")
    return directory


def _verified_content(directory, manifest, name):
    path = directory / name
    require(hashlib.sha256(path.read_bytes()).hexdigest() == manifest["outputs_sha256"][name],
            "Integridad de artefacto inválida")
    return path


def research_summary(directory):
    """Resultados agregados sellados; no habilita candidatos en la consulta."""
    directory = _artifact_directory(directory)
    require(directory.name == "sigard-principal-v3-experimental", "Resumen de investigación sólo V3")
    manifest = json.loads((directory / "manifest.private.json").read_text(encoding="utf-8"))
    metrics = json.loads(_verified_content(directory, manifest, "metrics.private.json").read_text(encoding="utf-8"))
    return dict(artifact_version=directory.name, external_validation_pending=True,
        selection_uses_development_only=True, probability_available=False, alerts_enabled=False,
        horizons={h: dict(development_rows=value["development_rows"], development_weeks=value["development_weeks"],
            validation_rows=value["development"]["validation_rows"], validation_weeks=value["development"]["validation_weeks"],
            selected=value["selection"]["selected"], best_ml=value["selection"]["best_ml"],
            promotion_approved=value["selection"]["promotion_approved"],
            counts={name: {k: row[k] for k in ("n", "mae", "rmse", "mean_bias")} for name, row in value["development"]["validation"].items()},
            presence=value["development"]["presence_validation"]["presence_score"])
            for h, value in metrics.items()})


def load_predictions(directory, *, method="selected"):
    directory = _artifact_directory(directory)
    require(method in ("selected", "persistence"), "Método no admitido para consulta")
    manifest = json.loads((directory / "manifest.private.json").read_text(encoding="utf-8"))
    name = ("persistence_predictions.private.parquet" if method == "persistence" and directory.name.endswith("v3-experimental")
            else "territorial_predictions.private.parquet")
    frame = pd.read_parquet(_verified_content(directory, manifest, name))
    quality_name = "quality_status.private.json"
    require(directory.name.endswith("v2-experimental") or quality_name in manifest["outputs_sha256"],
            "V3 requiere límites de calidad sellados")
    if quality_name in manifest["outputs_sha256"]:
        quality_path = _verified_content(directory, manifest, quality_name)
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        frame["presence_quality"] = quality["presence_quality"]
        methods = (dict.fromkeys(("1", "2", "4"), "lag_1_or_training_mean") if method == "persistence"
                   else quality.get("territorial_selected", {}))
        expected = frame.horizon_weeks.map(lambda h: methods.get(str(h), "territorial_reference_unspecified"))
        if "selected_method" in frame:
            require(frame.selected_method.eq(expected).all(), "Método inconsistente con el manifiesto")
        frame["selected_method"] = expected
        # V3 no promovida: sólo referencia; los candidatos se consultan como investigación.
        require(frame.selected_method.eq("lag_1_or_training_mean").all(),
                "El candidato ML requiere integración y promoción explícitas; use --research-summary")
    return frame


def main():
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="SIGARD: consulta privada de predicciones retrospectivas selladas")
    parser.add_argument("--artifacts", type=Path, default=root / "ml/artifacts/official/sigard-principal-v2-experimental")
    parser.add_argument("--date")
    parser.add_argument("--horizon", type=int, choices=[1, 2, 4], default=1)
    parser.add_argument("--radio")
    parser.add_argument("--list-dates", action="store_true")
    parser.add_argument("--method", choices=["selected", "persistence"], default="selected")
    parser.add_argument("--research-summary", action="store_true", help="Métricas V3 agregadas de desarrollo; no ejecuta modelos")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--map-output", type=Path, help="Exporta un HTML privado sin servidor; requiere build:predictive-viewer")
    args = parser.parse_args()
    try:
        require(not args.research_summary or not (args.map_output or args.list_dates or args.radio or args.date),
                "--research-summary no combina consultas territoriales")
        frame = None if args.research_summary else load_predictions(args.artifacts, method=args.method)
        if args.map_output:
            require(not args.output and not args.list_dates and not args.radio, "--map-output no combina exportación JSON ni filtro de radio")
            from sigard_ml.forecasting.local_map import export_private_map
            export_private_map(frame, args.map_output, initial_date=args.date, initial_horizon=args.horizon)
            print(json.dumps(dict(status="private_offline_map_created", private_output=str(args.map_output))))
            return 0
        if args.research_summary:
            result = research_summary(args.artifacts)
        elif args.list_dates:
            result = {str(h): sorted(str(value) for value in group.target_week.unique()) for h, group in frame.groupby("horizon_weeks")}
        else:
            require(args.date is not None, "Indique --date YYYY-MM-DD o --list-dates")
            result = query_predictions(frame, target_date=args.date, horizon_weeks=args.horizon, radio_id=args.radio)
        content = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if args.output:
            output = args.output.resolve()
            require(output.suffix == ".json" and any(output.is_relative_to(root / "data" / name) for name in ("interim/official", "processed/official")),
                    "La consulta sólo se exporta a un JSON privado bajo data/interim/official o data/processed/official")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                stream.write(content)
            print(json.dumps(dict(status=result.get("status", "available_dates") if isinstance(result, dict) else "saved", private_output=str(output))))
        else:
            print(content)
    except (ForecastError, OSError, KeyError, ValueError) as error:
        parser.exit(2, f"Consulta no disponible: {type(error).__name__}: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
