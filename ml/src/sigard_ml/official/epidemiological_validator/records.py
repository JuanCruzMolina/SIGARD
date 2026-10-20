"""Clasificación e identidad de filas; no infiere diagnósticos ni episodios."""

from collections import Counter

from sigard_ml.official.observed_settings import CLASSIFICATIONS, ROW_KEY
from .results import CheckResult as C, text


def validate_structure(record):
    missing = [name for name in ROW_KEY if not text(record.get(name))]
    return [C("record.key", "invalido" if missing else "valido",
              "Falta clave técnica de fila." if missing else "Clave de fila presente; no identifica un episodio.",
              ",".join(missing) if missing else "+".join(ROW_KEY))]


def validate_classification(record):
    category = record.get("classification")
    flag = record.get("epidemiological_eligibility_validated")
    results = []
    if flag is not None and type(flag) is not bool:
        results.append(C("classification.flag", "invalido", "La acreditación debe ser booleana.",
                         "epidemiological_eligibility_validated"))
    if category is None or category == "indeterminado":
        results.append(C("classification.state", "pendiente_acreditacion",
                         "Clasificación desconocida; no implica descarte ni negativo.", "classification"))
        if flag is True:
            results.append(C("classification.evidence", "invalido",
                             "Clasificación desconocida marcada como verificada.", "epidemiological_eligibility_validated"))
        return results
    if not isinstance(category, str) or category not in CLASSIFICATIONS:
        return results + [C("classification.state", "invalido", "Categoría fuera del contrato canónico.", "classification")]
    if not text(record.get("classification_rule_version")) or record.get("classification_mapped") is not True:
        results.append(C("classification.mapping", "invalido", "Falta correspondencia explícita y versionada.",
                         "classification_rule_version,classification_mapped"))
    if flag is True:
        backed = text(record.get("classification_evidence_ref"))
        results.append(C("classification.state", "valido" if backed else "pendiente_acreditacion",
                         "Acreditación declarada con referencia; no se revisó su contenido." if backed else
                         "Se declara verificación sin referencia de la decisión revisada.", "classification_evidence_ref"))
    else:
        results.append(C("classification.state", "advertencia",
                         "Clasificación registrada provisional; el literal no acredita el criterio histórico.", "classification"))
    return results


def validate_identity(record, *, repeated=False):
    results = []
    flags = ("possible_exact_duplicate", "possible_repeated_event_id", "identity_resolved_by_review",
             "identity_countable", "epidemiological_identity_validated")
    for name in flags:
        if name in record and type(record[name]) is not bool:
            results.append(C("episode.flag", "invalido", "La bandera de identidad debe ser booleana.", name))
    possible = repeated or any(record.get(name) is True for name in flags[:2])
    reviewed = record.get("identity_resolved_by_review") is True
    if reviewed:
        # La revisión del grupo completo sigue perteneciendo a episodes.py.
        complete = (text(record.get("episode_ref")) and text(record.get("identity_evidence_ref"))
                    and type(record.get("identity_countable")) is bool
                    and record.get("episode_status") in ("resolved_by_review", "resolved_nonrepresentative")
                    and record.get("identity_countable") == (record.get("episode_status") == "resolved_by_review")
                    and text(record.get("event_ref")))
        results.append(C("episode.resolution", "pendiente_acreditacion" if complete else "invalido",
                         "Resolución declarada: falta acreditar su aplicación al grupo completo." if complete else
                         "Resolución incompleta; no seleccionar representante automáticamente.", "identity_evidence_ref"))
    elif possible or not text(record.get("event_ref")):
        results.append(C("episode.identity", "pendiente_acreditacion",
                         "Posible repetición o identidad ausente; conservar filas sin deduplicar.", "event_ref"))
        if record.get("identity_countable") is True:
            results.append(C("episode.countable", "invalido", "Identidad pendiente marcada contable sin resolución.", "identity_countable"))
    else:
        results.append(C("episode.identity", "advertencia", "Identificador no repetido en esta entrada; episodio sólo provisional.", "event_ref"))
    if record.get("epidemiological_identity_validated") is True:
        results.append(C("episode.accreditation", "pendiente_acreditacion",
                         "Una fila o resolución técnica no acredita la definición epidemiológica del episodio.",
                         "epidemiological_identity_validated"))
    return results


def repeated_indices(records):
    """Repetición de claves e IDs opacos, sin leer ni agrupar datos personales."""
    keys = [tuple(row.get(name) for name in ROW_KEY) if all(text(row.get(name)) for name in ROW_KEY) else None
            for row in records]
    events = [row.get("event_ref") if text(row.get("event_ref")) else None for row in records]
    key_counts, event_counts = Counter(keys), Counter(events)
    return [(key is not None and key_counts[key] > 1, event is not None and event_counts[event] > 1)
            for key, event in zip(keys, events)]
