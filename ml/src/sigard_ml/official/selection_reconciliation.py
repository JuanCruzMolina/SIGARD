"""Cotejo local de selecciones: sólo agregados; HMAC e información de fila en RAM."""

from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import hmac
import json
import math
import unicodedata

VERSION = "official-original-selection-reconciliation-0.5b.2"
COUNT_FIELDS = (
    "original_records", "processed_records", "original_identifier_missing", "processed_identifier_missing",
    "literal_rule_selected", "literal_rule_excluded", "literal_rule_unknown",
    "selected_original_missing_identifier", "selected_original_without_processed_identifier_candidate",
    "selected_original_ambiguous_identifier_candidate", "selected_original_unique_identifier_candidate",
    "unrepresented_original_with_address_absent", "unrepresented_original_with_reference_date_unknown",
    "processed_without_original_identifier_candidate", "processed_ambiguous_identifier_candidates",
    "processed_unique_identifier_candidate", "unique_pairs_classification_changed",
    "unique_pairs_province_changed", "unique_pairs_department_changed",
    "unique_pairs_shared_classification_residence_equal", "processed_unique_pair_outside_literal_rule",
    "processed_unique_pair_literal_rule_unknown", "original_repeated_identifier_groups",
    "processed_repeated_identifier_groups", "original_records_in_repeated_identifier_groups",
    "processed_records_in_repeated_identifier_groups",
)


def literal(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, str) and value.startswith("="):
        return None  # No ejecutar fórmulas ni confundirlas con valores observados.
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return text if text else None


def identifier(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer() or abs(value) > 2**53:
            return None
        return str(int(value))
    return literal(value)


def protected_token(key, value):
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def canonical_text(value):
    value = literal(value)
    return " ".join(value.casefold().split()) if value is not None else None


def date_value(value):
    if isinstance(value, datetime):
        return value.date(), "valid"
    if type(value) is date:
        return value, "valid"
    text = literal(value)
    if text is None:
        return None, "missing_or_formula"
    if isinstance(value, (int, float, bool)):
        return None, "invalid_not_assumed_excel_serial"
    found = set()
    for format_string in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            found.add(datetime.strptime(text, format_string).date())
        except ValueError:
            pass
    if len(found) != 1:
        return None, "invalid_or_ambiguous"
    return found.pop(), "valid"


def project_record(values, columns, key, scope):
    """No recibe nombres/documentos/coordenadas como campos de cotejo.

    El domicilio sólo se convierte en presencia/ausencia. No conserva su texto.
    """
    def cell(field):
        index = columns.get(field)
        return values[index - 1] if index is not None and index <= len(values) else None
    event = identifier(cell("event_id"))
    address = cell("address")
    address_present = None if "address" not in columns or (isinstance(address, str) and address.startswith("=")) else literal(address) is not None
    classes = {name: literal(values[index - 1]) if index <= len(values) else None
               for name, index in columns.get("classification_columns", {}).items()}
    dates = {name: date_value(cell(name)) for name in ("symptom_onset", "sample_on", "notified_on", "updated_on") if name in columns}
    return {"key": protected_token(key, scope + "\0" + event) if event is not None else None,
        "cross_source_key": protected_token(key, "cross_source\0" + event) if event is not None else None,
        "classifications": classes, "province": canonical_text(cell("province")),
        "department": canonical_text(cell("department")),
        "address_present": address_present,
        "dates": dates}


def selection_state(record, rule):
    """Hipótesis literal reproducible; nunca equivale a confirmación clínica."""
    failures, unknown = [], []
    category = record["classifications"].get(rule["classification_field"])
    allowed = {canonical_text(value) for value in rule["accepted_classification_labels"]}
    if category is None:
        unknown.append("classification_missing_or_unmapped_column")
    elif canonical_text(category) not in allowed:
        failures.append("outside_explicit_literal_classification_rule")
    for field, accepted in (("province", rule["province_values"]), ("department", rule["department_values"])):
        value = record[field]
        if value is None:
            unknown.append(field + "_unknown")
        elif value not in {canonical_text(entry) for entry in accepted}:
            failures.append(field + "_outside_declared_residence_scope")
    if rule.get("require_valid_reference_date") is True:
        value, status = record["dates"].get(rule["reference_date_field"], (None, "unmapped"))
        if status != "valid":
            failures.append("explicit_required_date_unavailable")
    if rule.get("require_address_present") is True:
        if record["address_present"] is None:
            unknown.append("address_column_unmapped")
        elif not record["address_present"]:
            failures.append("explicit_required_address_absent")
    return (False if failures else None if unknown else True), failures, unknown


def profile(records):
    classification, residence, dates = defaultdict(Counter), Counter(), defaultdict(list)
    missing_address = sum(row["address_present"] is False for row in records)
    for row in records:
        for field, value in row["classifications"].items():
            classification[field][value] += 1
        residence[(row["province"], row["department"])] += 1
        for field, (value, status) in row["dates"].items():
            dates[field].append((value, status))
    return {"records": len(records), "missing_identifiers": sum(row["key"] is None for row in records),
        "classification_frequencies": {field: [{"literal_label": value, "records": count} for value, count in sorted(counts.items(), key=lambda item: str(item[0]))] for field, counts in sorted(classification.items())},
        "residence_frequencies": [{"province": values[0], "department": values[1], "records": count} for values, count in sorted(residence.items(), key=lambda item: str(item[0]))],
        "address_absent": missing_address, "address_unmapped": sum(row["address_present"] is None for row in records),
        "clinical_date_intervals": {field: {"valid_records": sum(status == "valid" for _, status in values),
            "unknown_records": sum(status != "valid" for _, status in values),
            "first": min((value for value, status in values if status == "valid"), default=None).isoformat() if any(status == "valid" for _, status in values) else None,
            "last": max((value for value, status in values if status == "valid"), default=None).isoformat() if any(status == "valid" for _, status in values) else None}
            for field, values in sorted(dates.items())},
        "observed_dates_prove_complete_coverage": False}


def compare(original, processed, rule, processed_classification_field=None):
    originals, current = defaultdict(list), defaultdict(list)
    for row in original:
        if row["key"] is not None:
            originals[row["key"]].append(row)
    for row in processed:
        if row["key"] is not None:
            current[row["key"]].append(row)
    states = [selection_state(row, rule) for row in original]
    counts = Counter({name: 0 for name in COUNT_FIELDS})
    reasons = Counter()
    counts["original_records"] = len(original)
    counts["processed_records"] = len(processed)
    counts["original_identifier_missing"] = sum(row["key"] is None for row in original)
    counts["processed_identifier_missing"] = sum(row["key"] is None for row in processed)
    for row, (state, failures, unknown) in zip(original, states, strict=True):
        counts["literal_rule_selected" if state is True else "literal_rule_excluded" if state is False else "literal_rule_unknown"] += 1
        reasons.update(failures + unknown)
        if state is True:
            if row["key"] is None:
                counts["selected_original_missing_identifier"] += 1
            elif row["key"] not in current:
                counts["selected_original_without_processed_identifier_candidate"] += 1
            elif len(originals[row["key"]]) != 1 or len(current[row["key"]]) != 1:
                counts["selected_original_ambiguous_identifier_candidate"] += 1
            else:
                counts["selected_original_unique_identifier_candidate"] += 1
        # Asociaciones observadas, no motivos causales inferidos del filtrado manual.
        if row["key"] is not None and row["key"] not in current:
            counts["unrepresented_original_with_address_absent"] += int(row["address_present"] is False)
            counts["unrepresented_original_with_reference_date_unknown"] += int(row["dates"].get(rule["reference_date_field"], (None, "unmapped"))[1] != "valid")
    matched_field = processed_classification_field or rule["classification_field"]
    for key, group in current.items():
        candidates = originals.get(key, [])
        if not candidates:
            counts["processed_without_original_identifier_candidate"] += len(group)
        elif len(candidates) != 1 or len(group) != 1:
            counts["processed_ambiguous_identifier_candidates"] += len(group)
        else:
            counts["processed_unique_identifier_candidate"] += 1
            before, after = candidates[0], group[0]
            changed_class = canonical_text(before["classifications"].get(rule["classification_field"])) != canonical_text(after["classifications"].get(matched_field))
            changed_province = before["province"] != after["province"]
            changed_department = before["department"] != after["department"]
            counts["unique_pairs_classification_changed"] += int(changed_class)
            counts["unique_pairs_province_changed"] += int(changed_province)
            counts["unique_pairs_department_changed"] += int(changed_department)
            counts["unique_pairs_shared_classification_residence_equal"] += int(not (changed_class or changed_province or changed_department))
            state, _, _ = selection_state(before, rule)
            counts["processed_unique_pair_outside_literal_rule"] += int(state is False)
            counts["processed_unique_pair_literal_rule_unknown"] += int(state is None)
    counts["original_repeated_identifier_groups"] = sum(len(group) > 1 for group in originals.values())
    counts["processed_repeated_identifier_groups"] = sum(len(group) > 1 for group in current.values())
    counts["original_records_in_repeated_identifier_groups"] = sum(len(group) for group in originals.values() if len(group) > 1)
    counts["processed_records_in_repeated_identifier_groups"] = sum(len(group) for group in current.values() if len(group) > 1)
    partition = sum(counts[name] for name in ("processed_identifier_missing", "processed_without_original_identifier_candidate", "processed_ambiguous_identifier_candidates", "processed_unique_identifier_candidate"))
    if partition != len(processed):
        raise ValueError("No concilian los grupos de registros procesados")
    return {"counts": dict(sorted(counts.items())), "exclusion_rule_reasons_non_additive": dict(sorted(reasons.items())),
        "identifier_match_proves_same_episode": False, "duplicates_deleted": False,
        "missing_dates_or_addresses_prove_manual_exclusion_reason": False,
        "clinical_confirmation_validated": False, "selection_status": "literal_rule_hypothesis_pending_semantic_validation",
        "identifiers_exported": False, "row_level_outputs_written": False}
