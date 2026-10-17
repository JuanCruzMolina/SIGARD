"""Controles descriptivos; no decide casos confirmados ni elimina registros."""

from collections import Counter
from datetime import date
import hashlib
import re

import pandas as pd

from sigard_ml.official.excel import value_type

from sigard_ml.official.geography import inspect_coordinates
from sigard_ml.official.normalization import DATE_FORMATS, normalize_text, parse_date
from sigard_ml.official.settings import (
    CLASSIFICATION_LABELS, DATE_ABSENCE_MARKERS, DATE_FIELDS, SENSITIVE_FIELDS,
    LOW_PRECISION_DECIMALS, normalize_header,
    DATE_FORMAT_PATTERNS, PRECISION_LABEL_WORDS,
    CLASSIFICATION_LABEL_WORDS,
)


def field_values(frame: pd.DataFrame, fields: dict, name: str) -> list:
    return frame[fields[name]].tolist() if name in fields else [None] * len(frame)


def count_label_words(labels, families):
    """Cuenta menciones literales; no valida el significado de las etiquetas."""
    tokens = [set(normalize_header(value).split()) for value in labels if value]
    return {name: sum(bool(words & candidates) for words in tokens) for name, candidates in families.items()}


def summarize_dates(values, *, as_of: date, formats=DATE_FORMATS):
    parsed = [parse_date(value, formats) for value in values]
    statuses = Counter(status for _, status in parsed)
    years = [value.year for value, status in parsed if status == "valid"]
    report = {"valid": statuses["valid"], "missing": statuses["missing"],
              "invalid_format": statuses["invalid_format"], "out_of_range": statuses["out_of_range"],
              "future": sum(value is not None and value > as_of for value, _ in parsed),
              "period_year_min": min(years) if years else None,
              "period_year_max": max(years) if years else None}
    report["invalid_values_matching_possible_absence_markers"] = sum(
        status == "invalid_format" and (normalize_text(raw) or "").lower() in DATE_ABSENCE_MARKERS
        for raw, (_, status) in zip(values, parsed, strict=True))
    patterns = Counter()
    for raw, (_, status) in zip(values, parsed, strict=True):
        if status != "invalid_format":
            continue
        text = normalize_text(raw) or ""
        pattern = next((name for name, regex in DATE_FORMAT_PATTERNS.items() if re.search(regex, text)), "other_unrecognized_format")
        patterns[pattern] += 1
    report["invalid_format_patterns"] = dict(patterns)
    report["invalid_value_types"] = dict(Counter(
        value_type(raw) for raw, (_, status) in zip(values, parsed, strict=True) if status == "invalid_format"))
    return parsed, report


def inspect_duplicates(frame, event_ids):
    """Dos señales separadas: repetición exacta de fila e ID de evento repetido."""
    row_signatures = []
    for values in frame.itertuples(index=False, name=None):
        signature = repr(tuple(normalize_text(value) for value in values)).encode("utf-8")
        row_signatures.append(hashlib.sha256(signature).hexdigest())
    row_counts = Counter(row_signatures)
    id_counts = Counter(value for value in event_ids if value is not None)
    exact_flags = [row_counts[value] > 1 for value in row_signatures]
    id_flags = [value is not None and id_counts[value] > 1 for value in event_ids]
    variants = {}
    for identifier, signature in zip(event_ids, row_signatures, strict=True):
        if identifier is not None:
            variants.setdefault(identifier, set()).add(signature)
    return exact_flags, id_flags, {
        "exact_duplicate_rows": sum(exact_flags),
        "repeated_event_id_rows": sum(id_flags),
        "repeated_event_id_groups": sum(count > 1 for count in id_counts.values()),
        "nonidentical_repeated_event_id_groups": sum(len(signatures) > 1 for signatures in variants.values()),
        "deduplication_performed": False,
    }


def validate_sheet(frame: pd.DataFrame, schema: dict, *, source_id: str, source_hash: str,
                   as_of: date, boundary=None, crs_confirmed=False, date_formats=DATE_FORMATS,
                   allowed_classifications=None, low_precision_decimals=LOW_PRECISION_DECIMALS):
    fields = schema["fields"]
    missing_columns = [name for name in ("event_id", "classification", "symptom_onset", "latitude", "longitude")
                       if name not in fields]
    date_results, date_reports = {}, {}
    for name in DATE_FIELDS:
        if name in fields:
            date_results[name], date_reports[name] = summarize_dates(
                field_values(frame, fields, name), as_of=as_of, formats=date_formats)
    event_ids = [normalize_text(value) for value in field_values(frame, fields, "event_id")]
    classifications = [normalize_text(value) for value in field_values(frame, fields, "classification")]
    precision_labels = [normalize_text(value) for value in field_values(frame, fields, "coordinate_precision")]
    geocoding_labels = [normalize_text(value) for value in field_values(frame, fields, "geocoding_status")]
    classification_labels = Counter(
        CLASSIFICATION_LABELS.get(normalize_header(value), "other_unmapped_label")
        for value in classifications if value is not None)
    exact_flags, id_flags, duplicates = inspect_duplicates(frame, event_ids)
    coordinates, geography_report = inspect_coordinates(
        field_values(frame, fields, "latitude"), field_values(frame, fields, "longitude"),
        boundary=boundary, crs_confirmed=crs_confirmed, low_precision_decimals=low_precision_decimals)
    normalized_rows = []
    chronology_issues = 0
    for index, (excel_row, identifier, classification, coordinate) in enumerate(
        zip(frame.index, event_ids, classifications, coordinates, strict=True)
    ):
        symptoms = date_results.get("symptom_onset", [(None, "missing")] * len(frame))[index]
        sample = date_results.get("sample_on", [(None, "missing")] * len(frame))[index]
        chronology_issues += int(symptoms[0] is not None and sample[0] is not None and sample[0] < symptoms[0])
        complete = (identifier is not None and classification is not None and symptoms[1] == "valid"
                    and symptoms[0] <= as_of and coordinate["coordinate_global_range_valid"])
        record_ref = hashlib.sha256(f"{source_hash}:{excel_row}".encode()).hexdigest()
        row = {"record_ref": record_ref, "source_id": source_id,
               "record_unit": "unresolved_source_record", "classification_label": classification,
               "event_id_present": identifier is not None, "structurally_complete": bool(complete),
               "coordinate_precision_label": precision_labels[index], "geocoding_status_label": geocoding_labels[index],
               "possible_exact_duplicate": exact_flags[index], "possible_repeated_event_id": id_flags[index],
               **coordinate}
        for name, results in date_results.items():
            row[name] = results[index][0]
            row[name + "_status"] = results[index][1]
        normalized_rows.append(row)
    valid = sum(row["structurally_complete"] for row in normalized_rows)
    allowed = set(allowed_classifications) if allowed_classifications is not None else None
    report = {
        "rows": len(frame), "columns": schema["columns"], "header_row": schema["header_row"],
        "fields": fields, "missing_required_columns": missing_columns,
        "sensitive_field_families": sorted(SENSITIVE_FIELDS.intersection(fields)),
        "structurally_complete": valid, "incomplete_or_invalid": len(frame) - valid,
        "methodology_review_required": len(frame), "case_eligibility_determined": False,
        "event_id_missing": sum(value is None for value in event_ids),
        "classification_missing": sum(value is None for value in classifications),
        "classification_nonempty": sum(value is not None for value in classifications),
        "distinct_classification_labels": len(set(value for value in classifications if value is not None)),
        "classification_literal_labels": dict(classification_labels),
        "classification_label_word_counts": count_label_words(classifications, CLASSIFICATION_LABEL_WORDS),
        "classification_domain_validated": allowed is not None,
        "classification_outside_configured_domain": sum(value is not None and value not in allowed
                                                        for value in classifications) if allowed is not None else None,
        "dates": date_reports, "sample_before_symptoms_needs_review": chronology_issues,
        "duplicates": duplicates, "geography": geography_report,
        "geocoding_status_missing": sum(normalize_text(value) is None for value in field_values(frame, fields, "geocoding_status")),
        "coordinate_precision_metadata_missing": sum(normalize_text(value) is None for value in field_values(frame, fields, "coordinate_precision")),
        "precision_label_word_counts": count_label_words(precision_labels, PRECISION_LABEL_WORDS),
    }
    # IDs originales se utilizan sólo en memoria para controles entre entregas.
    opaque_ids = [hashlib.sha256(value.encode()).hexdigest() if value is not None else None for value in event_ids]
    return pd.DataFrame(normalized_rows), report, opaque_ids
