"""Opciones editables de Fase 4.2; ninguna declaración prueba cobertura por sí sola."""

COVERAGE_VERSION = "official-weekly-coverage-0.4.2"
DATE_PANELS = ("strict", "expanded")
SCENARIOS = ("conservative", "exploratory")
VERIFIED_RULES = ("eligibility", "identity", "date_policy", "territorial_scope", "spatial_assignment")

COVERAGE_DEFAULTS = {
    "input_dir": "data/interim/official/observed/date_recovery_041",
    "output_dir": "data/interim/official/observed/coverage_042",
    "coverage_version": COVERAGE_VERSION,
    "zero_policy": {"enabled": True, "allow_declared_complete_in_exploratory": True},
    "provenance_declaration": {
        "declaration_ref": None,
        "delivery_statement": None,
        "manual_selection_statement": None,
        "selection_geographic_basis": "unknown",
        "requested_source_periods_documented": False,
        "temporal_completeness_automatically_verified": False,
    },
    "source_period_declarations": [],
    "coverage_declarations": [],
    "coverage_verifications": [],
    "diagnostic_activity_rule": {"min_positive_weeks": 8, "min_positive_cells": 30},
    "evaluation_start": "2024-01-07",
}
