"""Start the aggregate research API on 127.0.0.1:8765, without authentication."""

import hashlib
import os
from pathlib import Path

from .experimental_results import ROOT, ExperimentalResults, local_bytes

REGISTRY = Path("data/interim/official/spatial_app_session_v1/registry.private.json")


def main():
    if any(os.environ.get(k) for k in ("VERCEL", "RENDER", "RAILWAY_ENVIRONMENT", "WEBSITE_INSTANCE_ID", "K_SERVICE")) or Path("/.dockerenv").exists():
        raise SystemExit("La investigación sólo se inicia en el host local, fuera de despliegues y Docker")
    # Existing local authorization of fixed artifacts, not a browser credential.
    # Pin once at startup; every query revalidates these exact registry bytes.
    registry_hash = hashlib.sha256(local_bytes(ROOT, REGISTRY)).hexdigest()
    adapter = ExperimentalResults(REGISTRY, registry_hash)
    adapter.list_experiments()
    from .experimental_api import create_research_app
    import uvicorn

    # No host/port override, reload, workers, env app factory or proxy trust.
    uvicorn.run(create_research_app(adapter), host="127.0.0.1", port=8765,
                proxy_headers=False, access_log=False, server_header=False)


if __name__ == "__main__":
    main()
