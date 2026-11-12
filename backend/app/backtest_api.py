"""Installed only on the existing guarded loopback research listener."""
from fastapi import APIRouter, HTTPException, Request
from .experimental_results import ArtifactBlocked, InvalidDate, NotAvailable

PREFIX = '/api/v1/research/backtest'


def router_for(adapter, *, prefix=PREFIX, unified=False):
    router = APIRouter(prefix=prefix, include_in_schema=False)
    allowed_mode = {'disclosure'} if unified else set()

    def week_result(year, week, radio, disclosure):
        return adapter.week(year, week, radio, mode=disclosure) if unified else adapter.week(year, week, radio)

    def call(request, allowed, operation):
        if any(k not in allowed or len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            raise HTTPException(400, 'invalid_query')
        if adapter is None: raise HTTPException(503, 'backtest_bundle_unavailable')
        try: return operation()
        except InvalidDate: raise HTTPException(400, 'invalid_epi_period') from None
        except NotAvailable: raise HTTPException(404, 'territory_not_available') from None
        except (ArtifactBlocked, KeyError, ValueError, TypeError, OSError):
            raise HTTPException(503, 'backtest_artifacts_blocked') from None

    @router.get('/calendar')
    def calendar(request: Request): return call(request, set(), adapter.catalog if adapter else None)

    @router.get('/geometry')
    def geometry(request: Request): return call(request, set(), adapter.geometry if adapter else None)

    @router.get('/metadata')
    def metadata(request: Request): return call(request, set(), adapter.metadata if adapter else None)

    @router.get('/comparison')
    def comparison(request: Request, year: str, week: str, radio: str | None = None, disclosure: str = 'presentation'):
        return call(request, {'year', 'week', 'radio'} | allowed_mode, lambda: week_result(year, week, radio, disclosure))

    @router.get('/predicted')
    def predicted(request: Request, year: str, week: str, radio: str | None = None, disclosure: str = 'presentation'):
        result = call(request, {'year', 'week', 'radio'} | allowed_mode, lambda: week_result(year, week, radio, disclosure))
        result['rows'] = [{k: row[k] for k in ('radio_id', 'predicted', 'baseline', 'availability_status', 'territorial_quality', 'ml', 'ml_availability') if k in row} for row in result['rows']]
        result.pop('department'); result.pop('metrics'); return result

    @router.get('/observed')
    def observed(request: Request, year: str, week: str, radio: str | None = None, disclosure: str = 'presentation'):
        result = call(request, {'year', 'week', 'radio'} | allowed_mode, lambda: week_result(year, week, radio, disclosure))
        result['rows'] = [{k: row[k] for k in ('radio_id', 'observed', 'coverage_status', 'zero_provenance', 'territorial_quality')} for row in result['rows']]
        result.pop('metrics'); return result

    @router.get('/metrics')
    def metrics(request: Request, year: str, week: str, radio: str | None = None, disclosure: str = 'presentation'):
        result = call(request, {'year', 'week', 'radio'} | allowed_mode, lambda: week_result(year, week, radio, disclosure))
        result.pop('rows'); return result

    @router.get('/history')
    def history(request: Request, start: str, end: str, radio: str | None = None, disclosure: str = 'presentation'):
        return call(request, {'start', 'end', 'radio'} | allowed_mode,
                    lambda: adapter.history(start, end, radio, mode=disclosure) if unified else adapter.history(start, end, radio))

    return router
