"""Append deterministic reviews to the existing private database; never reimport."""
import argparse
import json
import sys
from pathlib import Path

from sigard_ml.ingestion.db_import import private_output
from sigard_ml.ingestion.epidemiology.db import connect
from sigard_ml.ingestion.epidemiology.resolution import resolve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    try:
        output = private_output(args.report)
        config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        if config.get('status') != 'approved' or not config.get('authorization_ref'):
            raise ValueError('review_authorization_required')
        with connect() as conn:
            result = resolve(conn, version=config['version'],
                evidence=dict(config['evidence'], authorization_ref=config['authorization_ref']),
                extraction_declarations=config.get('extraction_declarations'))
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(status='complete', private_report_written=True)))
        return 0
    except Exception:
        print(json.dumps(dict(status='blocked_or_failed', reason='check_private_review_contract')), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
