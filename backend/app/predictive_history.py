"""Precomputed annual histories of the predictive module (offline bundle, read-only API).

The annual series of the whole territory (one per calendar year and disclosure mode) is the
slowest response of the visor: computing it means projecting and protecting every week of the
year. It is built offline with the same service code and stored as hash-pinned files:

- every file is listed in the history manifest with its SHA-256 and read with the existing
  per-process verification (`local_bytes`); an altered file or manifest blocks the response;
- the manifest binds the exact inputs: the backtest registry, each ML overlay registry and the
  SHA-256 of the code that produced the history. Any change blocks until the bundle is rebuilt;
- with the bundle installed, the API never recomputes an annual history: it only reads and
  verifies. Other ranges and single-radio histories are still projected per request.

No training, inference, SQL or source-data access. Output is create-only below
data/interim/official (private, ignored by Git).
"""
import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from .backtest_results import CONTEXT
from .experimental_results import ROOT, local_bytes, require

SCHEMA = 'sigard-predictive-history/1'
MODES = ('presentation', 'private')
PRIVATE_ROOT = 'data/interim/official/'
LIMIT = 16 * 1024 * 1024
_APP = Path(__file__).resolve().parent
# The history is a deterministic function of these modules and the pinned bundles.
CODE_FILES = ('predictive_service.py', 'backtest_results.py', 'predictive_ml.py', 'predictive_history.py')


def code_sha256():
    digest = hashlib.sha256()
    for name in CODE_FILES:
        # Line endings are normalized so a checkout setting does not invalidate the bundle.
        digest.update(name.encode() + b'\0' + (_APP / name).read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return digest.hexdigest()


def bindings(service):
    reader = service.reader
    require(reader is not None)
    return {'backtest_registry_sha256': reader.registry_sha256,
            'ml_registries_sha256': [sha for _, sha in service.ml_registries],
            'code_sha256': code_sha256()}


def year_bounds(catalog):
    bounds = {}
    for week in catalog['weeks']:
        first, _ = bounds.get(week['target_year'], (week['target_week'], None))
        bounds[week['target_year']] = (first, week['target_week'])
    return bounds


def encode(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class HistoryStore:
    """Serves annual histories only from the verified, input-bound manifest."""
    def __init__(self, root, registry_path, registry_sha256):
        self.root = Path(root).resolve(); self.registry_path = Path(registry_path); self.registry_sha256 = registry_sha256

    def _manifest(self, service):
        pin = json.loads(local_bytes(self.root, self.registry_path, self.registry_sha256))
        path = Path(pin['path'])
        require(path.as_posix().startswith(PRIVATE_ROOT))
        manifest = json.loads(local_bytes(self.root, path, pin['sha256']))
        require(manifest['schema_version'] == SCHEMA and manifest['training_performed'] is False
                and manifest['inference_performed'] is False)
        # Stale against any input (bundle, overlays or code) -> blocked, never served.
        require(manifest['bindings'] == bindings(service))
        return path.parent, manifest

    def history(self, service, catalog, start, end, mode):
        folder, manifest = self._manifest(service)
        require(manifest['context'] == {k: catalog[k] for k in CONTEXT})
        entry = manifest['years'].get(next((str(y) for y, b in year_bounds(catalog).items() if b == (start, end)), ''))
        # An annual range of the catalog must exist in the bundle: it is never recomputed.
        require(entry is not None and (entry['start'], entry['end']) == (start, end))
        name = entry['files'][mode]
        require(isinstance(name, str) and re.fullmatch(r'history/\d{4}\.(presentation|private)\.private\.json', name) is not None)
        document = json.loads(local_bytes(self.root, folder / name, manifest['files'][name], LIMIT))
        require(document['start'] == start and document['end'] == end and document['selected_radio'] is None
                and document['disclosure']['mode'] == mode and document['module_version'] == manifest['module_version'])
        return document


def build(service, output, *, root=ROOT, today=None):
    """Compute every annual history with the service code and write a create-only bundle."""
    root = Path(root).resolve(); output = Path(output)
    require(not output.is_absolute() and output.as_posix().startswith(PRIVATE_ROOT) and '..' not in output.parts)
    folder = root / output
    require(not folder.exists())
    require(service.history_store is None)  # always computed, never copied from a previous bundle
    from .predictive_service import MODULE, DISCLOSURE
    catalog = service._snapshot().catalog()
    files = {}; years = {}; documents = {}
    for year, (start, end) in sorted(year_bounds(catalog).items()):
        years[str(year)] = {'start': start, 'end': end, 'files': {}}
        for mode in MODES:
            name = f'history/{year}.{mode}.private.json'
            body = encode(service.history(start, end, None, mode))
            require(len(body) <= LIMIT)
            documents[name] = body; files[name] = hashlib.sha256(body).hexdigest(); years[str(year)]['files'][mode] = name
    manifest = {'schema_version': SCHEMA, 'module_version': MODULE, 'disclosure_policy': DISCLOSURE,
                'context': {k: catalog[k] for k in CONTEXT}, 'bindings': bindings(service),
                'generated_at': str(today or date.today()), 'training_performed': False, 'inference_performed': False,
                'scope': 'annual_whole_territory_history_per_disclosure_mode', 'years': years, 'files': files}
    (folder / 'history').mkdir(parents=True)
    for name, body in documents.items():
        (folder / name).write_bytes(body)
    manifest_body = encode(manifest)
    (folder / 'manifest.private.json').write_bytes(manifest_body)
    registry = encode({'path': (output / 'manifest.private.json').as_posix(), 'sha256': hashlib.sha256(manifest_body).hexdigest()})
    (folder / 'registry.private.json').write_bytes(registry)
    return {'registry': (output / 'registry.private.json').as_posix(), 'registry_sha256': hashlib.sha256(registry).hexdigest(),
            'files': len(files), 'years': sorted(years)}


def compare(stored_service, computed_service):
    """Stored annual history == freshly computed one, for every year and mode. Returns counts only."""
    catalog = computed_service._snapshot().catalog(); checked = 0
    for start, end in year_bounds(catalog).values():
        for mode in MODES:
            stored = stored_service.history(start, end, None, mode)
            computed = json.loads(encode(computed_service.history(start, end, None, mode)))
            require(stored == computed); checked += 1
    return checked


def _local_service(history=False):
    from . import research_local as local
    from .backtest_results import BacktestResults
    from .predictive_service import PredictiveService
    pin = lambda path: hashlib.sha256(local_bytes(ROOT, path)).hexdigest()
    reader = BacktestResults(local.BACKTEST_REGISTRY, pin(local.BACKTEST_REGISTRY))
    ml = [(path, pin(path)) for path in (local.ML_REGISTRY, local.ML_V2_REGISTRY) if (ROOT / path).exists()]
    store = HistoryStore(ROOT, local.HISTORY_REGISTRY, pin(local.HISTORY_REGISTRY)) if history else None
    return PredictiveService(reader, ml_registries=ml, history_store=store)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Historia anual precalculada del módulo predictivo (local, privada).')
    parser.add_argument('command', choices=('build', 'verify'))
    args = parser.parse_args(argv)
    from . import research_local as local
    if args.command == 'build':
        result = build(_local_service(), local.HISTORY_REGISTRY.parent)
        print(json.dumps({k: result[k] for k in ('files', 'years')}))
    else:
        print(json.dumps({'identical_annual_histories': compare(_local_service(True), _local_service())}))


if __name__ == '__main__':
    main()
