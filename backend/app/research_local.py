"""Start the aggregate research API on 127.0.0.1:8765, without authentication."""

import hashlib
import os
from pathlib import Path

from .experimental_results import ROOT, local_bytes

REGISTRY = Path("data/interim/official/spatial_app_session_v1/registry.private.json")
BACKTEST_REGISTRY = Path("data/interim/official/historical-backtest-session-v1/registry.private.json")
CONTEXT_REGISTRY = Path("data/interim/official/predictive-context-session-v1/registry.private.json")
ML_REGISTRY = Path("data/interim/official/ml-integration-stage3-20261103-v1/registry.private.json")


def main():
    if any(os.environ.get(k) for k in ("VERCEL", "RENDER", "RAILWAY_ENVIRONMENT", "WEBSITE_INSTANCE_ID", "K_SERVICE")) or Path("/.dockerenv").exists():
        raise SystemExit("La investigación sólo se inicia en el host local, fuera de despliegues y Docker")
    # Final flow never imports A/B inference or loads historical estimators.
    from .backtest_results import BacktestResults
    backtest = None
    if (ROOT / BACKTEST_REGISTRY).exists():
        backtest_hash = hashlib.sha256(local_bytes(ROOT, BACKTEST_REGISTRY)).hexdigest()
        backtest = BacktestResults(BACKTEST_REGISTRY, backtest_hash)
    from .predictive_service import PredictiveService
    context_hash = hashlib.sha256(local_bytes(ROOT, CONTEXT_REGISTRY)).hexdigest() if (ROOT / CONTEXT_REGISTRY).exists() else None
    ml_hash = hashlib.sha256(local_bytes(ROOT, ML_REGISTRY)).hexdigest() if (ROOT / ML_REGISTRY).exists() else None
    predictive = PredictiveService(backtest, context_registry=CONTEXT_REGISTRY if context_hash else None,
                                   context_sha256=context_hash, ml_registry=ML_REGISTRY if ml_hash else None, ml_sha256=ml_hash)
    from .experimental_api import create_research_app
    import uvicorn

    # No host/port override, reload, workers, env app factory or proxy trust.
    uvicorn.run(create_research_app(predictive=predictive, legacy=False), host="127.0.0.1", port=8765,
                proxy_headers=False, access_log=False, server_header=False)


if __name__ == "__main__":
    main()
