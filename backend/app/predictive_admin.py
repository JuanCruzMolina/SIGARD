"""Predictive viewer routes on the local administrative API (127.0.0.1:8767). Never deployment.

F2: this is the only installation of `/api/v1/research/predictive/*`. It is attached
exclusively by `alerts_local` (local host); `app.main` and any deployment never import it
and never open the predictive artifacts. Each request passes, in this order:

1. the local guard of the former research API (loopback client, exact Host and Origin,
   GET/OPTIONS only, no forwarded headers, `X-Sigard-Research: local-read`);
2. a DB-verified administrator JWT (`security.get_current_admin`: role, active account
   and `token_version`, so revoked sessions get 401);
3. for exact values (`disclosure=private`), an audit row with user, time, route and the
   requested week/period. Returned values are never copied. If the row cannot be
   written the query fails (closed). Protected (`presentation`) queries are not audited.

Responses keep the `sigard-predictive-experimental/2` contract, the minimum-5 cell
protection, the per-request integrity checks and the per-process caches of the service.
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, Request
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, insert
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

from .database import get_db
from .experimental_results import ROOT, local_bytes
from .models import User
from .security import get_current_admin

PREFIX = "/api/v1/research/predictive"
ORIGIN = "http://127.0.0.1:5173"
AUTHORITY = "127.0.0.1:8767"
READ_HEADER = "x-sigard-research"
PREFLIGHT_HEADERS = {"authorization", READ_HEADER}
# Viewer requests run CPU-bound work in the shared threadpool of this process. Admitting at
# most this many at once keeps threads free for login, reports and alerts (the queued viewer
# requests wait without holding a thread); the work is GIL-bound, so throughput is unchanged.
VIEWER_CONCURRENCY = 6

BACKTEST_REGISTRY = Path("data/interim/official/historical-backtest-session-v1/registry.private.json")
CONTEXT_REGISTRY = Path("data/interim/official/predictive-context-session-v1/registry.private.json")
ML_REGISTRY = Path("data/interim/official/ml-integration-stage3-20261103-v1/registry.private.json")
ML_V2_REGISTRY = Path("data/interim/official/ml-integration-v2-20261114-v1/registry.private.json")
HISTORY_REGISTRY = Path("data/interim/official/predictive-history-v1/registry.private.json")

# Local-only table (own metadata, like demo_workspace): never part of app.main's schema
# or of the managed Alembic chain. It stores who/when/what was asked, never results.
metadata = MetaData()
audit = Table(
    "predictive_view_audit", metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_user_id", Integer, nullable=False),
    Column("route", String(20), nullable=False),
    Column("period", String(48), nullable=False),
    Column("radio", String(20), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)


def build_service(root=ROOT):
    """Same construction as the former `research_local` launcher (pinned registries)."""
    from .backtest_results import BacktestResults
    from .predictive_history import HistoryStore
    from .predictive_service import PredictiveService

    digest = lambda path: hashlib.sha256(local_bytes(root, path)).hexdigest()
    backtest = BacktestResults(BACKTEST_REGISTRY, digest(BACKTEST_REGISTRY)) if (root / BACKTEST_REGISTRY).exists() else None
    context = digest(CONTEXT_REGISTRY) if (root / CONTEXT_REGISTRY).exists() else None
    ml = [(path, digest(path)) for path in (ML_REGISTRY, ML_V2_REGISTRY) if (root / path).exists()]
    history = (HistoryStore(root, HISTORY_REGISTRY, digest(HISTORY_REGISTRY))
               if backtest is not None and (root / HISTORY_REGISTRY).exists() else None)
    return PredictiveService(backtest, context_registry=CONTEXT_REGISTRY if context else None,
                             context_sha256=context, ml_registries=ml, history_store=history)


def _clip(value, size):
    return (value or "")[:size]


def viewer_admin(request: Request, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)) -> User:
    query = request.query_params
    if query.get("disclosure") == "private":
        route = _clip(request.url.path.removeprefix(PREFIX + "/"), 20)
        period = (f"{_clip(query.get('year'), 8)}-SE{_clip(query.get('week'), 4)}" if "year" in query
                  else f"{_clip(query.get('start'), 10)}..{_clip(query.get('end'), 10)}")
        db.execute(insert(audit).values(actor_user_id=admin.id, route=route, period=period,
                                        radio=_clip(query.get("radio"), 20) or None,
                                        created_at=datetime.now(timezone.utc)))
        db.commit()
    return admin


def _guarded(path):
    return path == PREFIX or path.startswith(PREFIX + "/")


SECURITY_HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"}


class PredictiveGate:
    """Outermost pure ASGI layer of the local admin app for the viewer prefix.

    Requests under PREFIX pass the local guard here and are dispatched to a dedicated
    sub-application (router + admin dependency) without crossing the administrative app's
    other middlewares, so large responses are not re-streamed by each of them. Every other
    path continues to the administrative app unchanged.
    """

    def __init__(self, app, viewer, concurrency=VIEWER_CONCURRENCY):
        import asyncio
        self.app, self.viewer = app, viewer
        self.slots = asyncio.Semaphore(concurrency)

    @staticmethod
    def _decision(request):
        headers = request.headers
        host = request.client.host if request.client else None
        forwarded = any(k.lower().startswith(("forwarded", "x-forwarded", "x-real-ip")) for k in headers)
        local = (host == "127.0.0.1" and len(headers.getlist("host")) == 1 and headers.get("host") == AUTHORITY
                 and request.url.scheme == "http" and not forwarded)
        trusted = (len(headers.getlist("origin")) == 1 and headers.get("origin") == ORIGIN
                   and headers.get("sec-fetch-site") in {None, "same-origin", "same-site"})
        if not local or not trusted:
            return False, JSONResponse({"detail": "local_research_only"}, status_code=403)
        if request.method == "OPTIONS":
            # Preflight answered here: only GET with Authorization and the read header.
            requested = {h.strip().lower() for h in headers.get("access-control-request-headers", "").split(",") if h.strip()}
            if headers.get("access-control-request-method") != "GET" or not requested <= PREFLIGHT_HEADERS:
                return True, JSONResponse({"detail": "invalid_preflight"}, status_code=400)
            return True, Response(status_code=200, headers={
                "Access-Control-Allow-Methods": "GET", "Access-Control-Allow-Headers": "Authorization, X-Sigard-Research",
                "Access-Control-Max-Age": "600"})
        if request.method != "GET":
            return True, JSONResponse({"detail": "read_only_api"}, status_code=405, headers={"Allow": "GET, OPTIONS"})
        if len(headers.getlist(READ_HEADER)) != 1 or headers.get(READ_HEADER) != "local-read":
            return True, JSONResponse({"detail": "local_read_header_required"}, status_code=403)
        return True, None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _guarded(scope["path"]):
            return await self.app(scope, receive, send)
        from starlette.datastructures import MutableHeaders
        from starlette.requests import Request

        cors, response = self._decision(Request(scope))

        async def secured(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in SECURITY_HEADERS.items():
                    headers[key] = value
                if cors:
                    headers["Access-Control-Allow-Origin"] = ORIGIN
                    headers.add_vary_header("Origin")
            await send(message)

        if response is not None:
            return await response(scope, receive, secured)
        async with self.slots:
            await self.viewer(scope, receive, secured)


def mount(app, service):
    """Attach the viewer routes, the audit table and the local guard to the local admin app."""
    from fastapi import FastAPI
    from .backtest_api import router_for

    metadata.create_all(app.state.engine)
    app.state.predictive_service = service
    viewer = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    viewer.state.SessionLocal = app.state.SessionLocal  # same administrative database (get_db)
    viewer.include_router(router_for(service, prefix=PREFIX, unified=True, dependencies=[Depends(viewer_admin)]))
    # Added last, so it is the outermost layer: requests that fail the guard never reach
    # authentication, the database or the service.
    app.add_middleware(PredictiveGate, viewer=viewer)
    return viewer
