"""API independiente en memoria; no se importa desde pipelines oficiales."""

from .coverage import validate_label, validate_week
from .dates import validate_dates
from .records import repeated_indices, validate_classification, validate_identity, validate_structure
from .results import CheckResult, VERSION
from .spatial import validate_spatial


def validate_records(records):
    """Una lista de controles por fila; índices posicionales, sin publicar claves."""
    records = list(records)
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Se requiere una secuencia de diccionarios de registros")
    output = []
    for record, (duplicate_key, repeated_event) in zip(records, repeated_indices(records)):
        checks = validate_structure(record)
        if duplicate_key:
            checks.append(CheckResult("record.unique_key", "invalido", "Clave técnica de fila repetida; no implica episodio duplicado.", "source_id,sheet_ref,record_ref"))
        checks += validate_classification(record)
        checks += validate_identity(record, repeated=repeated_event)
        checks += validate_dates(record)
        checks += validate_spatial(record)
        output.append(checks)
    return output


__all__ = ["CheckResult", "VERSION", "validate_records", "validate_week", "validate_label"]
