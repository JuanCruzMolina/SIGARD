"""Reglas editables de Fase 4; no equivalen a una validación epidemiológica."""

OBSERVED_VERSION = "official-observed-exploration-0.4.1"
CLASSIFICATION_VERSION = "classification-explicit-0.4.0"
ELIGIBILITY_VERSION = "eligibility-conservative-0.4.0"
EPISODE_VERSION = "episode-identifiers-0.4.0"
CLASSIFICATIONS = {"confirmado", "probable", "sospechoso", "descartado", "indeterminado"}
ROW_KEY = ["source_id", "sheet_ref", "record_ref"]

# Claves literales completas. Sólo se normalizan Unicode, mayúsculas y espacios.
# Ninguna búsqueda de palabras o fragmentos determina una clasificación.
CLASSIFICATION_MAP = {
    "Confirmado": "confirmado", "Caso confirmado": "confirmado",
    "Caso confirmado DEN-1": "confirmado", "Caso confirmado DEN-2": "confirmado",
    "Caso confirmado sin serotipo": "confirmado",
    "Caso confirmado por nexo epidemiológico autóctono": "confirmado",
    "Caso confirmado por nexo epidemiológico importado": "confirmado",
    "Probable": "probable", "Caso probable": "probable",
    "Sospechoso": "sospechoso", "Caso sospechoso": "sospechoso",
    "Descartado": "descartado", "Caso descartado": "descartado",
    "Caso descartado por diagnostico diferencial": "descartado",
    "Caso descartado por diagnóstico diferencial": "descartado",
    "Indeterminado": "indeterminado", "Sin clasificar": "indeterminado",
}

OBSERVED_DEFAULTS = {
    "output_dir": "data/interim/official/observed",
    "spatial_dir": "data/interim/official/geography",
    "cartography": "data/processed/territorial_master.parquet",
    "period_start": "2020-01-01",
    "period_end": "2024-12-31",
    "classification_version": CLASSIFICATION_VERSION,
    "classification_map": CLASSIFICATION_MAP,
    "eligibility_version": ELIGIBILITY_VERSION,
    "exploratory_include": ["confirmado"],
    "exploratory_exclude": ["probable", "sospechoso", "descartado"],
    "episode_version": EPISODE_VERSION,
    "episode_resolutions": [],
    "reference_date_field": "symptom_onset",
    "date_hierarchy": None,
    "date_rule_version": "symptom-onset-no-fallback-0.4.0",
    "coverage": [],
    "coverage_version": "coverage-unverified-0.4.0",
    "geocoding_acceptance_ref": "project-phase4-approximate-location-decision",
    "geocoder_providers_declared": ["Nominatim", "Georef"],
    "auxiliary_columns": [],
}
