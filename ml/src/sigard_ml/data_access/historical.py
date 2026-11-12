"""Explicit opt-in for frozen file-based research, never an ML fallback."""
import sys


def require_historical(enabled):
    if enabled is not True:
        raise ValueError('historical_reproduction_only_use_postgres_pipeline')


def parse_file_args(parser):
    """Keep old synthetic/departmental experiments explicitly historical."""
    parser.add_argument('--historical-reproduction', action='store_true')
    args = parser.parse_args()
    if not args.historical_reproduction:
        parser.error('File-based experiment is historical only; operational ML uses PostgreSQL')
    return args


def database_default(family):
    if '--historical-reproduction' not in sys.argv:
        import json
        print(json.dumps(dict(status='archived',family=family,training_performed=False,
            reason='final_module_uses_frozen_h1_references_only',
            reproduction='explicit_historical_reproduction_and_original_authorization_required')))
        return 2
    return None
