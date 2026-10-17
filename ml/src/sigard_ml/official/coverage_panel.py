"""Deriva cobertura y ceros sin cambiar registros, fechas ni asignaciones de Fase 4.1."""

import pandas as pd

from sigard_ml.official.calendar import weeks_between
from sigard_ml.official.coverage_policy import coverage_map, decide_observation
from sigard_ml.official.coverage_settings import COVERAGE_VERSION
from sigard_ml.official.observed_panel import pending_counts
from sigard_ml.official.weekly_targets import attach_next_week_target


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
