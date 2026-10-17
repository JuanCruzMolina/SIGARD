"""Etiquetas de cobertura asumida autorizada; nunca modifica conteos ni entrena."""

from datetime import date, timedelta

import pandas as pd

from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.splits import DEFAULT_PLANS, class_counts, prepare_splits
from sigard_ml.official.weekly_targets import validate_targets

VERSION = "official-assumed-label-scenario-0.5b.3.0"
ZERO_KIND = "cero_asumido_experimental"


def validate_authorization(entry):
    """Contrato propio: una asunción no se hace pasar por completitud verificada."""
    required = {"version", "declaration_ref", "responsible_ref", "decision_ref", "justification",
                "start", "end", "source_ids", "radio_scope", "date_policy", "coverage_kind",
                "materialization_authorized", "training_authorized", "pending_policy",
                "ready_universe_records", "clinical_confirmation_inferred"}
    if set(entry) != required or entry["version"] != VERSION:
        raise ValueError("Contrato de autorización inválido")
    if any(not isinstance(entry[key], str) or not entry[key].strip()
           for key in ("declaration_ref", "responsible_ref", "decision_ref", "justification")):
        raise ValueError("Falta la decisión explícita del responsable")
    if (entry["coverage_kind"] != "assumed_experimental_not_verified"
            or entry["materialization_authorized"] is not True
            or entry["training_authorized"] is not False
            or entry["clinical_confirmation_inferred"] is not False
            or entry["date_policy"] != "expanded"
            or entry["pending_policy"] != "preserve_all_existing_blockers"
            or entry["source_ids"] != ["delivery_2024_2026"]
            or entry["radio_scope"] != "all_263_capital_radios"
            or entry["ready_universe_records"] != 7720):
        raise ValueError("Acciones o alcance no autorizados")
    start, end = (date.fromisoformat(entry[key]) for key in ("start", "end"))
    # Esta versión implementa exclusivamente la decisión concreta de esta fase.
    if (start, end) != (date(2024, 1, 7), date(2024, 6, 8)):
        raise ValueError("Intervalo distinto de la autorización vigente")
    return start, end


def materialize_labels(panel, authorization):
    start, end = validate_authorization(authorization)
    if (panel.empty or panel.duplicated(KEYS).any() or panel[KEYS].isna().any().any()
            or not panel.panel_fechas.eq("expanded").all()):
        raise ValueError("Panel vacío, duplicado o política de fechas incorrecta")
    validate_targets(panel)
    pending = panel.registros_pendientes_posibles
    if (pending.isna().any() or pending.lt(0).any() or not pending.mod(1).eq(0).all()
            or panel.ventana_semanal_parcial.isna().any()
            or not panel.ventana_semanal_parcial.isin([True, False]).all()):
        raise ValueError("Bloqueos desconocidos o inválidos")
    if not panel.fecha_fin_semana.eq(panel.fecha_inicio_semana.map(lambda day: day + timedelta(days=6))).all():
        raise ValueError("Semana incompatible con calendario")
    # Nunca sumar huecos ni proyectar supuestos como conteos observados.
    in_scope = panel.fecha_inicio_semana.ge(start) & panel.fecha_fin_semana.le(end)
    candidate = (in_scope & panel.casos_observados.isna() & pending.eq(0)
                 & ~panel.ventana_semanal_parcial)
    weekly = panel[KEYS + ["fecha_fin_semana", "casos_observados",
                         "registros_pendientes_posibles", "ventana_semanal_parcial"]].copy()
    weekly["en_intervalo_autorizado"] = in_scope
    weekly["ausencia_asumida_autorizada"] = candidate
    weekly["tipo_ausencia"] = pd.Series(None, index=panel.index, dtype="object")
    weekly.loc[candidate, "tipo_ausencia"] = ZERO_KIND
    weekly["conteo_observado_modificado"] = False
    target = weekly.rename(columns={"fecha_inicio_semana": "fecha_inicio_semana_objetivo",
        "fecha_fin_semana": "fecha_fin_semana_objetivo",
        "registros_pendientes_posibles": "pendientes_semana_objetivo",
        "ventana_semanal_parcial": "semana_objetivo_parcial",
        "casos_observados": "conteo_original_semana_objetivo"})
    columns = KEYS + ["fecha_inicio_semana_objetivo", "objetivo_semana_siguiente", "objetivo_valido",
                      "objetivo_provisional", "objetivo_con_fecha_aproximada", "escenario", "panel_fechas"]
    labels = panel[columns].copy().rename(columns={"escenario": "escenario_origen"})
    labels["objetivo_original"] = labels.objetivo_semana_siguiente
    labels = labels.merge(target.drop(columns=["conteo_observado_modificado"]),
        on=["radio_censal", "fecha_inicio_semana_objetivo"], how="left", validate="one_to_one")
    # Un objetivo sin celda t+1 permanece desconocido: no se salta a otra semana.
    assumed = labels.ausencia_asumida_autorizada.eq(True) & labels.objetivo_original.isna()
    labels.loc[assumed, "objetivo_semana_siguiente"] = 0
    labels["objetivo_semana_siguiente"] = labels.objetivo_semana_siguiente.astype("Int8")
    labels["objetivo_valido"] = labels.objetivo_semana_siguiente.notna()
    labels.loc[assumed, "objetivo_provisional"] = True
    labels["tipo_etiqueta"] = "desconocida"
    labels.loc[labels.objetivo_original.eq(1).fillna(False), "tipo_etiqueta"] = "positivo_provisional"
    labels.loc[labels.objetivo_original.eq(0).fillna(False), "tipo_etiqueta"] = "cero_heredado_bajo_politica_origen"
    labels.loc[assumed, "tipo_etiqueta"] = ZERO_KIND
    labels["cobertura_asumida_no_verificada"] = assumed
    labels["autorizacion_cobertura_ref"] = pd.Series(None, index=labels.index, dtype="object")
    labels.loc[labels.en_intervalo_autorizado.eq(True), "autorizacion_cobertura_ref"] = authorization["declaration_ref"]
    labels["escenario"] = "experimental_assumed_ready_2024_v1"
    labels["apto_entrenamiento"] = False
    validate_targets(labels)
    known = labels.objetivo_original.notna()
    if not labels.loc[known, "objetivo_original"].eq(labels.loc[known, "objetivo_semana_siguiente"]).all():
        raise ValueError("Se alteró una etiqueta conocida")
    changed = labels.objetivo_original.isna() & labels.objetivo_semana_siguiente.notna()
    if not changed.eq(assumed).all():
        raise ValueError("Cambio fuera de los negativos autorizados")
    return labels.sort_values(KEYS).reset_index(drop=True), weekly.sort_values(KEYS).reset_index(drop=True)


def distribution(labels, grouping):
    rows = []
    for value, group in labels.groupby(grouping, sort=True, dropna=False):
        counts = class_counts(group.objetivo_semana_siguiente)
        rows.append({grouping: value, "rows": len(group), **counts,
            "assumed_negative": int(group.tipo_etiqueta.eq(ZERO_KIND).sum()),
            "unknown_with_pending": int((group.objetivo_semana_siguiente.isna()
                                         & group.pendientes_semana_objetivo.gt(0)).sum()),
            "positive_with_pending": int((group.objetivo_semana_siguiente.eq(1)
                                          & group.pendientes_semana_objetivo.gt(0)).sum()),
            "approximate_positive": int((group.objetivo_semana_siguiente.eq(1)
                                         & group.objetivo_con_fecha_aproximada).sum())})
    return pd.DataFrame(rows)


def chronological_review(labels):
    # Los planes heredados se auditan, sin habilitarlos automáticamente.
    # El plan acotado conserva las fronteras de origen ya propuestas en Fase 5A.
    plans = [*DEFAULT_PLANS, {"name": "authorized_2024_only", "validation_start": "2024-03-03",
        "test_start": "2024-05-05", "end": "2024-06-09"}]
    parts, diagnostics = [], []
    for plan in plans:
        assignments, _ = prepare_splits(labels, [plan])
        joined = assignments.merge(labels, on=KEYS, validate="one_to_one", suffixes=("_split", ""))
        if plan["name"] == "authorized_2024_only":
            joined.loc[~joined.en_intervalo_autorizado.eq(True), "partition"] = "outside_authorized_interval"
        stats = {}
        for name in ("train", "validation", "test"):
            group = joined[joined.partition.eq(name)]
            counts = class_counts(group.objetivo_semana_siguiente)
            known = counts["positive"] + counts["negative"]
            stats[name] = {"rows": len(group), **counts,
                "assumed_negative": int(group.tipo_etiqueta.eq(ZERO_KIND).sum()),
                "both_classes": min(counts["positive"], counts["negative"]) > 0,
                "positive_fraction_known": counts["positive"] / known if known else None,
                "target_weeks": int(group.fecha_inicio_semana_objetivo.nunique()),
                "positive_target_weeks": int(group.loc[group.objetivo_semana_siguiente.eq(1), "fecha_inicio_semana_objetivo"].nunique()),
                "negative_target_weeks": int(group.loc[group.objetivo_semana_siguiente.eq(0), "fecha_inicio_semana_objetivo"].nunique()),
                "first_origin": str(group.fecha_inicio_semana.min()) if len(group) else None,
                "last_target_end": str(group.fecha_fin_semana_objetivo.max()) if len(group) else None}
        both = all(value["both_classes"] for value in stats.values())
        joined["label_known"] = joined.objetivo_semana_siguiente.notna()
        joined["eligible_for_future_supervised_use"] = False
        parts.append(joined[KEYS + ["plan", "partition", "label_known", "eligible_for_future_supervised_use"]])
        diagnostics.append({**plan, "partitions": stats, "both_classes_in_every_partition": both,
            "status": "classes_present_pending_training_authorization" if both else "not_fit_missing_class",
            "training_authorized": False, "operational_validation": False,
            "sample_size_scientifically_validated": False,
            "purged_or_outside": int((~joined.partition.isin(stats)).sum())})
    return pd.concat(parts, ignore_index=True), diagnostics
