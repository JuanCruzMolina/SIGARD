"""Cobertura y etiquetas como entradas separadas; no genera ceros ni etiquetas."""

from sigard_ml.official.coverage_policy import decide_observation
from .dates import validate_week_fields
from .results import CheckResult as C, count, text


def validate_week(row):
    results = validate_week_fields(row, year_field="anio_epidemiologico", number_field="semana_epidemiologica",
                                   start_field="fecha_inicio_semana", end_field="fecha_fin_semana")
    if not text(row.get("radio_censal")):
        results.append(C("coverage.key", "invalido", "Falta radio de la celda semanal.", "radio_censal"))
    declared, verified = row.get("cobertura_declarada"), row.get("cobertura_comprobada")
    for field, state, reference in (("cobertura_declarada", declared, "declaracion_cobertura_ref"),
                                     ("cobertura_comprobada", verified, "verificacion_cobertura_ref")):
        if state not in ("complete", "partial", "unknown"):
            results.append(C("coverage.state", "invalido", "Estado de cobertura ausente o desconocido.", field))
        elif state != "unknown":
            results.append(C("coverage.provenance", "valido" if text(row.get(reference)) else "invalido",
                             "Referencia de procedencia conservada." if text(row.get(reference)) else "Indicador de cobertura sin procedencia.", reference))
    raw, pending, partial = (row.get(name) for name in
                            ("registros_elegibles_provisionales", "registros_pendientes_posibles", "ventana_semanal_parcial"))
    observed = row.get("casos_observados")
    if (not count(raw) or not count(pending) or type(partial) is not bool
            or (observed is not None and not count(observed))):
        return results + [C("coverage.structure", "invalido", "Conteos, pendientes o parcialidad ausentes o inválidos; no asumir cero.",
                            "registros_elegibles_provisionales,registros_pendientes_posibles,ventana_semanal_parcial,casos_observados")]
    scenario = row.get("escenario")
    if declared not in ("complete", "partial", "unknown") or verified not in ("complete", "partial", "unknown") or scenario not in ("conservative", "exploratory"):
        return results + [C("coverage.policy", "invalido", "Escenario o cobertura fuera del contrato.", "escenario")]
    policy = row.get("zero_policy")
    if not isinstance(policy, dict) or set(policy) != {"enabled", "allow_declared_complete_in_exploratory"} or any(type(v) is not bool for v in policy.values()):
        return results + [C("coverage.policy", "invalido", "Proveer la política de ceros existente de forma explícita.", "zero_policy")]
    try:
        expected, coverage, state, provisional = decide_observation(raw, pending, declared, verified, scenario,
                                                                   partial_window=partial, zero_policy=policy)
    except ValueError:
        return results + [C("coverage.policy", "invalido", "Escenario o cobertura fuera del contrato.", "escenario")]
    coherent = (observed == expected and row.get("estado_cobertura") == coverage
                and row.get("estado_observacion") == state and type(row.get("cero_provisional")) is bool
                and row["cero_provisional"] == provisional)
    results.append(C("coverage.consistency", "valido" if coherent else "invalido",
                     "Estados conservan la decisión de cobertura existente." if coherent else
                     "Conteo/estado incompatible: ausencia de filas no habilita cero y pendientes bloquean negativos.", "casos_observados,estado_observacion,estado_cobertura,cero_provisional"))
    if expected is None:
        results.append(C("coverage.unknown", "pendiente_acreditacion", "Semana desconocida: conservar null, incluidos los pendientes.", "casos_observados"))
    elif expected > 0:
        results.append(C("coverage.positive", "advertencia", "Presencia de registros provisionales; no acredita episodios únicos ni conteo completo.", "casos_observados"))
    elif provisional:
        results.append(C("coverage.declared_zero", "advertencia", "Cero declarado provisional; mantener separado de ausencia acreditada.", "cero_provisional"))
    if verified != "unknown":
        results.append(C("coverage.accreditation", "pendiente_acreditacion",
                         "Verificación declarada: validar evidencia mediante coverage_policy.validate_evidence en una integración autorizada.", "verificacion_cobertura_ref"))
    if not text(row.get("version_cobertura")):
        results.append(C("coverage.version", "invalido", "Falta versión de cobertura.", "version_cobertura"))
    return results


def validate_label(row):
    """Entrada del objetivo t+1 de assumed_scenario, nunca la celda de origen."""
    kind, value = row.get("tipo_etiqueta"), row.get("objetivo_semana_siguiente")
    expected = {"desconocida": None, "positivo_provisional": 1, "cero_asumido_experimental": 0,
                "cero_heredado_bajo_politica_origen": 0}
    if (not isinstance(kind, str) or kind not in expected or value != expected[kind]
            or (value is not None and type(value) is not int)):
        return [C("label.state", "invalido", "Etiqueta/valor incompatibles; desconocido no puede convertirse en negativo.", "tipo_etiqueta,objetivo_semana_siguiente")]
    if type(row.get("objetivo_valido")) is not bool or row["objetivo_valido"] != (value is not None):
        return [C("label.known", "invalido", "objetivo_valido sólo indica etiqueta conocida.", "objetivo_valido")]
    if kind == "desconocida":
        return [C("label.unknown", "pendiente_acreditacion", "Objetivo desconocido conservado como null.", "objetivo_semana_siguiente")]
    if kind == "positivo_provisional":
        return [C("label.positive", "advertencia", "Positivo provisional; no es confirmación epidemiológica acreditada.", "tipo_etiqueta")]
    if kind == "cero_heredado_bajo_politica_origen":
        return [C("label.inherited_zero", "pendiente_acreditacion", "Revisar cobertura de la celda objetivo original con validate_week; no usar la cobertura del origen.", "tipo_etiqueta")]
    valid = (row.get("cobertura_asumida_no_verificada") is True
             and text(row.get("autorizacion_cobertura_ref"))
             and row.get("en_intervalo_autorizado") is True
             and type(row.get("pendientes_semana_objetivo")) is int and row["pendientes_semana_objetivo"] == 0
             and row.get("semana_objetivo_parcial") is False
             and row.get("conteo_original_semana_objetivo") is None
             and row.get("objetivo_original") is None)
    return [C("label.experimental", "advertencia" if valid else "invalido",
              "Negativo experimental identificado, sin alterar conteo original ni acreditar ausencia." if valid else
              "Negativo experimental sin procedencia/alcance, con pendientes, semana parcial o valor original alterado.", "tipo_etiqueta"),
            C("label.authorization", "pendiente_acreditacion", "La referencia no acredita contenido ni alcance: revisar la autorización existente antes de cualquier uso.", "autorizacion_cobertura_ref")]
