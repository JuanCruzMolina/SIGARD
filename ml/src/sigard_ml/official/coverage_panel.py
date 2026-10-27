"""Deriva cobertura y ceros sin cambiar registros, fechas ni asignaciones de Fase 4.1."""

from numbers import Integral

import pandas as pd

from sigard_ml.official.calendar import weeks_between
from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from sigard_ml.official.classification import CONFIRMED_RECORD_TARGET
from sigard_ml.official.coverage_policy import coverage_map, decide_observation
from sigard_ml.official.coverage_settings import COVERAGE_VERSION
from sigard_ml.official.observed_panel import pending_counts
from sigard_ml.official.weekly_targets import attach_next_week_target


def principal_provisional_counts(panel, classification_inventory, *, territory_ids,
                                 territory_version, source_versions, extraction_date):
    """Proyecta positivos históricos agregados sin reconstruir P2/P3/P5.

    Sin IO ni grilla nueva. Devuelve también celdas exteriores para conciliarlas.
    No permite inferir clasificación/fuente desde resúmenes incompatibles.
    La autorización y verificación de huellas pertenecen al llamador.
    """
    from datetime import date

    ids = list(territory_ids)
    if (territory_version != "la-rioja-46014010-256-v1" or len(ids) != 256
            or len(set(ids)) != 256 or not all(isinstance(x, str) and x for x in ids)):
        raise ValueError("Se requiere el universo operativo de 256 radios verificado")
    if type(extraction_date) is not date:
        raise ValueError("La extracción declarada requiere fecha explícita")
    required = {"radio_censal", "anio_epidemiologico", "semana_epidemiologica",
                "fecha_inicio_semana", "fecha_fin_semana", "casos_observados",
                "fuentes_con_registros", "ventana_semanal_parcial", "estado_cobertura",
                "cobertura_declarada", "cobertura_comprobada", "registros_pendientes_posibles",
                "registros_asignacion_incierta", "version_fecha"}
    if not required <= set(panel) or panel.duplicated(["radio_censal", "fecha_inicio_semana"]).any():
        raise ValueError("Panel agregado incompleto o duplicado")
    counts = panel.casos_observados.dropna()
    if not counts.map(lambda x: isinstance(x, Integral) and not isinstance(x, bool) and x >= 0).all():
        raise ValueError("Los registros deben ser enteros no negativos")
    inventory_fields = {"source_id", "canonical_category", "included_provisional"}
    if not inventory_fields <= set(classification_inventory):
        raise ValueError("Falta inventario agregado de clasificación")
    inventory_counts = classification_inventory.included_provisional
    if not inventory_counts.map(lambda x: isinstance(x, Integral) and not isinstance(x, bool) and x >= 0).all():
        raise ValueError("Inventario de inclusión inválido")
    eligible = classification_inventory[inventory_counts.gt(0)]
    if not eligible.canonical_category.eq("confirmado").all():
        raise ValueError("El inventario no acredita clasificación homogénea de los incluidos")
    expected = eligible.groupby("source_id").included_provisional.sum().to_dict()
    actual, rows = {}, []
    for row in panel.loc[panel.casos_observados.gt(0).fillna(False)].itertuples():
        sources = list(row.fuentes_con_registros)
        if len(sources) != 1 or sources[0] not in source_versions:
            raise ValueError("Fuente mixta o sin versión: no repartir conteos")
        source = sources[0]
        version = source_versions[source]
        if not isinstance(version, str) or not version.strip():
            raise ValueError("Falta versión de fuente")
        if any(not isinstance(x, Integral) or isinstance(x, bool)
               for x in (row.anio_epidemiologico, row.semana_epidemiologica)):
            raise ValueError("Año y semana deben ser enteros")
        year, week = int(row.anio_epidemiologico), int(row.semana_epidemiologica)
        start, end = DEFAULT_CALENDAR.week_bounds(year, week)
        if (row.fecha_inicio_semana != start or row.fecha_fin_semana != end
                or bool(row.ventana_semanal_parcial) or end > extraction_date):
            raise ValueError("Semana incompatible con calendario oficial o extracción")
        if not isinstance(row.radio_censal, str) or not row.radio_censal:
            raise ValueError("Radio candidato no utilizable")
        count = int(row.casos_observados)
        uncertain = row.registros_asignacion_incierta
        pending = row.registros_pendientes_posibles
        if any(not isinstance(x, Integral) or isinstance(x, bool) or x < 0 for x in (uncertain, pending)) or uncertain > count:
            raise ValueError("Estados agregados de incertidumbre inválidos")
        actual[source] = actual.get(source, 0) + count
        rows.append(dict(epidemiological_year=year, epidemiological_week=week,
            week_start=start, week_end=end, radio_id=row.radio_censal,
            territory_version=territory_version,
            territory_status="included" if row.radio_censal in ids else "outside",
            provisional_positive_records=count, classification="confirmado",
            target_definition=CONFIRMED_RECORD_TARGET, count_unit="provisional_record_count",
            data_kind="epidemiological_provisional_records", maturity="unknown",
            accredited_episode_count=None, P2_status="unknown_or_unresolved",
            P3_status="not_accredited", coverage_state=row.estado_cobertura,
            declared_coverage=row.cobertura_declarada, verified_coverage=row.cobertura_comprobada,
            possible_pending_record_mentions=int(pending), pending_mentions_not_additive=True,
            P5_status="provisional_approximate_attribution_not_accredited",
            uncertain_assignment_records=int(uncertain), source_id=source, source_version=version,
            extraction_date=extraction_date, available_on=None, date_policy_version=row.version_fecha,
            calendar_version=DEFAULT_CALENDAR.version,
            transformation_version="principal-provisional-record-projection-1",
            training_eligible=False))
    if actual != expected:
        raise ValueError("Panel e inventario de incluidos no concilian por fuente")
    if not rows:
        raise ValueError("No hay positivos agregados que proyectar")
    return pd.DataFrame(rows).sort_values(["radio_id", "week_start"]).reset_index(drop=True)


def build_coverage_panel(base, audit, options, *, date_panel, scenario, period_start, period_end, repo_root=None):
    keys = ["radio_censal", "fecha_inicio_semana"]
    if base.duplicated(keys).any():
        raise ValueError("Panel base duplicado")
    radios = sorted(base.radio_censal.unique())
    weeks = weeks_between(period_start, period_end)
    expected = {(radio, week.start) for radio in radios for week in weeks}
    if set(base[keys].itertuples(index=False, name=None)) != expected:
        raise ValueError("La grilla anterior no coincide con su período")
    included = audit[audit.processing_outcome.eq("included")]
    if int(base.registros_elegibles_provisionales.sum()) != len(included):
        raise ValueError("El panel base no concilia con su auditoría")
    # Reutiliza la incertidumbre temporal amplia de Fase 4: sin fecha no se
    # restringe a un año de archivo ni a los extremos de fechas observadas.
    cells, by_radio, by_week, global_pending = pending_counts(audit, radios, weeks)
    declarations = coverage_map(options["coverage_declarations"], radios, weeks, date_panel)
    verifications = coverage_map(options["coverage_verifications"], radios, weeks, date_panel,
                                 verified=True, repo_root=repo_root)
    approximate = included[included.fecha_aproximada].groupby(["radio_candidate", "week_start"]).size().to_dict()
    rows = []
    for row in base.itertuples():
        key = row.radio_censal, row.fecha_inicio_semana
        pending = cells[key] + by_radio[row.radio_censal] + by_week[row.fecha_inicio_semana] + global_pending
        if pending != row.registros_pendientes_posibles:
            raise ValueError("Los pendientes de Fase 4.1 no concilian")
        raw_count = 0 if pd.isna(row.registros_elegibles_provisionales) else int(row.registros_elegibles_provisionales)
        declared, declaration_ref = declarations.get(key, ("unknown", None))
        verified, verification_ref = verifications.get(key, ("unknown", None))
        count, coverage, state, provisional_zero = decide_observation(raw_count, pending, declared, verified, scenario,
            partial_window=row.ventana_semanal_parcial, zero_policy=options["zero_policy"])
        geographic_quality = ("asignacion_aproximada_incierta" if row.registros_asignacion_incierta else
                              "candidato_geometrico_sin_validacion_epidemiologica") if raw_count else "sin_registros_asignados"
        rows.append({"radio_censal": row.radio_censal, "fraccion_censal": row.fraccion_censal,
            "anio_epidemiologico": row.anio_epidemiologico, "semana_epidemiologica": row.semana_epidemiologica,
            "fecha_inicio_semana": row.fecha_inicio_semana, "fecha_fin_semana": row.fecha_fin_semana,
            "casos_observados": count, "estado_cobertura": coverage, "estado_observacion": state,
            "cobertura_declarada": declared, "cobertura_comprobada": verified,
            "declaracion_cobertura_ref": declaration_ref, "verificacion_cobertura_ref": verification_ref,
            "ventana_semanal_parcial": row.ventana_semanal_parcial, "registros_pendientes_posibles": pending,
            "registros_fecha_aproximada": int(approximate.get(key, 0)),
            "registros_asignacion_incierta": row.registros_asignacion_incierta,
            "tipos_geocodificacion": row.tipos_geocodificacion, "fuentes_con_registros": row.fuentes_con_registros,
            "escenario": scenario, "panel_fechas": date_panel, "calidad_geografica": geographic_quality,
            "cero_provisional": provisional_zero, "conteo_provisional": True,
            "unidad_conteo": "registros_elegibles_provisionales_no_casos_unicos_validados",
            "version_cobertura": options["coverage_version"], "version_fecha": row.version_fecha,
            "version_asignacion_geografica": row.version_asignacion_geografica,
            "version_transformacion": COVERAGE_VERSION, "validado": False,
            "disponibilidad_historica": "no_reconstruida"})
    result = pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)
    result["casos_observados"] = result.casos_observados.astype("Int64")
    if int(result.casos_observados.sum()) != len(included):
        raise ValueError("Los conteos se alteraron al generar cobertura")
    result = attach_next_week_target(result)
    validate_coverage_panel(result)
    return result


def validate_coverage_panel(panel):
    counts = panel.casos_observados
    if counts.dropna().lt(0).any():
        raise ValueError("Conteo negativo")
    zeros = counts.eq(0).fillna(False)
    if (panel.loc[zeros, "registros_pendientes_posibles"].ne(0).any()
        or panel.loc[zeros, "ventana_semanal_parcial"].any()
        or not panel.loc[zeros, "estado_cobertura"].isin(["completa_comprobada", "completa_declarada_provisional"]).all()):
        raise ValueError("Cero sin cobertura suficiente o con pendientes")
    conservative = zeros & panel.escenario.eq("conservative")
    if not panel.loc[conservative, "cobertura_comprobada"].eq("complete").all():
        raise ValueError("Cero conservador sin cobertura comprobada")
    declared = zeros & panel.estado_cobertura.eq("completa_declarada_provisional")
    if not panel.loc[declared, "cero_provisional"].all() or not panel.loc[declared, "escenario"].eq("exploratory").all():
        raise ValueError("Cero declarado sin marcar su condición provisional")
