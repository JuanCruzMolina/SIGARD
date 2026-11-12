"""Read-only final lifecycle registry. This module cannot train or select."""
import json

VERSION = 'sigard-final-lifecycle-20261102-v1'
REGISTRY = dict(version=VERSION, horizon_weeks=1, training_enabled=False, operational_enabled=False,
    active_references=['presence_seasonal','count_latest'],
    not_promoted=['rf_A_reference','rf_A_epi_climate','rf_A_epi_no_climate','residual_h1'],
    archived=['A_original','B','Poisson_V1_V2_core','V3_h2','V3_h4','historical_discarded_variants'],
    blocked=['current_2025_2026','official_health_alerts'],
    climate_usage='context_only_selected_references_use_no_climate_predictors',
    historical_reproduction='explicit_module_cli_with_historical_reproduction_flag_and_original_authorization')


def main():
    print(json.dumps(REGISTRY));return 0


if __name__=='__main__':raise SystemExit(main())
