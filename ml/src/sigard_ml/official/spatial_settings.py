"""Parámetros de fase 3; las distancias de sondeo NO son errores estimados."""

SPATIAL_VERSION = "official-geography-0.3.0"
EXCHANGE_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:32719"
EXPECTED_RADIOS = 263
CAPITAL_PREFIX = "46014"
# Tolerancia numérica de la proyección para diagnóstico (0,2%), no error de geocodificación.
MAX_METRIC_SCALE_DEVIATION = 0.002
SPATIAL_DEFAULTS = {
    "cartography": "data/processed/territorial_master.parquet",
    "territorial_config": "ml/configs/territorial_master.json",
    "output_dir": "data/interim/official/geography",
    "assumed_crs": EXCHANGE_CRS,
    "boundary_review_m": None,
    "sensitivity_distances_m": [10, 25, 50, 100],
    "documented_uncertainty_m": None,
    "uncertainty_evidence_ref": None,
    "geocoding_provenance_ref": None,
    "location_role": "unknown",
}
