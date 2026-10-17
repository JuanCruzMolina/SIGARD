"""Fase 5B: prepara candidatos declarados; no materializa conteos/etiquetas."""

from datetime import date, timedelta

import pandas as pd

from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.universe import declaration_readiness


def declared_coverage_preview(panel, declarations, source_ids, *, date_policy, materialize=False):
    if materialize is not False:
        raise ValueError("Fase 5B no autoriza materializar negativos")
    readiness = declaration_readiness(declarations, source_ids)
    if date_policy not in {"strict", "expanded"} or panel.duplicated(KEYS).any():
        raise ValueError("Política de fechas o claves inválidas")
    if not panel.panel_fechas.eq(date_policy).all():
        raise ValueError("La declaración no corresponde al panel temporal")
    refs = pd.Series(None, index=panel.index, dtype="object")
    declared = pd.Series(False, index=panel.index)
    for entry in declarations:
        # Una declaración no puede ampliar los períodos documentados de extracción.
        first, last = date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"])
        intervals = sorted((date.fromisoformat(row["requested_start"]), date.fromisoformat(row["requested_end"]))
                           for row in entry["source_extractions"])
        cursor = first
        for start, end in intervals:
            if start <= cursor <= end:
                cursor = max(cursor, end + timedelta(days=1))
        if cursor <= last:
            raise ValueError("La declaración excede períodos de extracción documentados")
        if date_policy not in entry["date_panels"]:
            continue
        scope = panel.fecha_inicio_semana.ge(first) & panel.fecha_fin_semana.le(last)
        if (scope & declared).any():
            raise ValueError("Declaraciones superpuestas")
        declared |= scope
        refs.loc[scope] = entry["declaration_ref"]
    candidate = (declared & panel.casos_observados.isna() & panel.registros_pendientes_posibles.eq(0)
                 & ~panel.ventana_semanal_parcial & panel.anio_epidemiologico.le(2024))
    lookup = dict(zip(panel[KEYS].itertuples(index=False, name=None), candidate, strict=True))
    result = panel[KEYS].copy()
    result["declared_interval"] = declared
    result["declaration_ref"] = refs
    result["candidate_observation_if_separately_authorized"] = candidate
    result["candidate_target_if_separately_authorized"] = [
        lookup.get((radio, start + timedelta(days=7)), False)
        for radio, start in result[KEYS].itertuples(index=False, name=None)]
    result["scenario"] = "experimental_assumed_preview_only"
    result["materialization_authorized"] = False
    return result, {"declaration_readiness": readiness,
        "declared_intervals": len(declarations), "candidate_observations": int(candidate.sum()),
        "candidate_targets": int(result.candidate_target_if_separately_authorized.sum()),
        "assumed_zeros_materialized": False, "labels_modified": False,
        "conservative_scenario_modified": False, "training_authorized": False,
        "further_gates": ["explicit project-responsible declaration with sources, periods, filters and case definition",
            "source/extraction reconciliation and eligibility review", "documentary evidence and responsible signature",
            "separate explicit authorization to materialize an experimental scenario",
            "preserve pending blockers, partial weeks, positives and unknowns outside declared scope",
            "version new private experimental panel separately; never replace conservative labels"]}


def eligibility_review(audit, *, source_2022="delivery_2022"):
    required = {"source_id", "classification", "processing_outcome", "analysis_eligibility",
                "epidemiological_eligibility_validated", "epidemiological_identity_validated"}
    if not required <= set(audit):
        raise ValueError("Faltan campos de validación de elegibilidad")
    included = audit.processing_outcome.eq("included")
    # Clasificación literal no reemplaza validación epidemiológica/identidad.
    validated = (included & audit.classification.eq("confirmado")
                 & audit.analysis_eligibility.eq("eligible_provisional")
                 & audit.epidemiological_eligibility_validated.eq(True)
                 & audit.epidemiological_identity_validated.eq(True))
    working = audit[["source_id", "classification", "processing_outcome"]].copy()
    working["clinically_validated_confirmed"] = validated
    inventory = working.groupby(["source_id", "classification", "processing_outcome"], sort=True).agg(
        records=("source_id", "size"), clinically_validated_confirmed=("clinically_validated_confirmed", "sum")).reset_index()
    source = audit[audit.source_id.eq(source_2022)]
    return inventory, {"included_records_provisional": int(included.sum()),
        "confirmed_under_existing_validation_flags": int(validated.sum()),
        "source_2022": {"source_id": source_2022, "rows": len(source),
            "included_provisional": int(source.processing_outcome.eq("included").sum()),
            "canonical_classifications": {str(key): int(value) for key, value in source.classification.value_counts().items()},
            "universe_and_clinical_criterion_resolved": False},
        "rows_reclassified": False, "new_confirmed_cases_declared": False,
        "interpretation": "Only existing explicit eligibility and identity validation flags could justify confirmed terminology; current provisional positives are not automatically confirmed",
        "required_review": ["historical dengue definition and confirmation criterion by extraction",
            "literal confirmation filter and event-field semantics for source 2022",
            "reconcile pre-filter export, omissions and source classifications",
            "identity/episodes, original vs approximate dates, residence and pending records"]}
