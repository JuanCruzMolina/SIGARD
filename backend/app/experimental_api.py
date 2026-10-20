"""Read-only aggregate API, installed exclusively by the loopback launcher."""

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from .experimental_results import ArtifactBlocked, NotAvailable

PREFIX = "/api/v1/research/spatial"
ORIGIN = "http://127.0.0.1:5173"
AUTHORITY = "127.0.0.1:8765"
READ_HEADER = "x-sigard-research"


def create_research_app(adapter):
    # No database, admin/report routes, credentials, sessions or static file mounts.
    application = FastAPI(title="SIGARD · Investigación local", docs_url=None,
                          redoc_url=None, openapi_url=None)
    application.add_middleware(
        CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=False,
        allow_methods=["GET"], allow_headers=["X-Sigard-Research"],
    )
    router = APIRouter(prefix=PREFIX, include_in_schema=False)

    def query(request, allowed):
        if any(key not in allowed for key in request.query_params) or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise HTTPException(400, "invalid_query")

    def call(operation):
        try:
            return operation()
        except NotAvailable:
            raise HTTPException(404, "not_available") from None
        except ArtifactBlocked:
            raise HTTPException(503, "experimental_artifacts_blocked") from None

    @router.get("/models")
    def models(request: Request):
        query(request, set())
        return call(adapter.list_experiments)

    @router.get("/models/{model}/weeks")
    def weeks(model: str, request: Request):
        query(request, set())
        catalog = call(adapter.list_experiments)
        entry = next((m for m in catalog["models"] if m["model_id"] == model), None)
        if entry is None:
            raise HTTPException(404, "not_available")
        return {"schema_version": catalog["schema_version"], **entry}

    @router.get("/models/{model}/scores/{target}")
    def scores(model: str, target: str, request: Request, experiment_id: str):
        query(request, {"experiment_id"})
        return call(lambda: adapter.get_retrospective_scores(model, experiment_id, target))

    @router.get("/comparison/{target}/{radio}")
    def comparison(target: str, radio: str, request: Request):
        query(request, set())
        return call(lambda: adapter.compare(radio, target))

    @router.get("/evaluation")
    def evaluation(request: Request):
        query(request, set())
        return call(adapter.get_evaluation)

    @router.get("/history/{radio}")
    def history(radio: str, request: Request):
        query(request, set())
        return call(lambda: adapter.history(radio))

    application.include_router(router)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.middleware("http")
    async def local_research_guard(request, call_next):
        host = request.client.host if request.client else None
        forwarded = any(k.lower().startswith(("forwarded", "x-forwarded", "x-real-ip")) for k in request.headers)
        local = (host == "127.0.0.1" and len(request.headers.getlist("host")) == 1
                 and request.headers.get("host") == AUTHORITY
                 and request.url.scheme == "http" and not forwarded)
        trusted_origin = (len(request.headers.getlist("origin")) == 1
                          and request.headers.get("origin") == ORIGIN
                          and request.headers.get("sec-fetch-site") in {None, "same-origin", "same-site"})
        research = request.url.path.startswith("/api/v1/research")
        if not local or (research and not trusted_origin):
            response = JSONResponse({"detail": "local_research_only"}, status_code=403)
        elif request.method not in {"GET", "OPTIONS"}:
            response = JSONResponse({"detail": "read_only_api"}, status_code=405, headers={"Allow": "GET, OPTIONS"})
        elif research and request.method != "OPTIONS" and (
            len(request.headers.getlist(READ_HEADER)) != 1 or request.headers.get(READ_HEADER) != "local-read"
        ):
            response = JSONResponse({"detail": "local_read_header_required"}, status_code=403)
        else:
            response = await call_next(request)
        if local and trusted_origin and "Access-Control-Allow-Origin" not in response.headers:
            response.headers["Access-Control-Allow-Origin"] = ORIGIN
            response.headers.add_vary_header("Origin")
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    return application
