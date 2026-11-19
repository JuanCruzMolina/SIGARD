"""Every administrative route requires the admin role; the public surface is an explicit list."""

from fastapi.routing import APIRoute

from app.security import get_current_admin

PUBLIC = {
    "POST /api/v1/citizen-reports", "GET /api/v1/citizen-reports/status/{tracking_code}", "POST /api/v1/geocoding/address",
    "GET /api/v1/public/weeks", "GET /api/v1/public/predictions/{cutoff_date}", "GET /api/v1/public/territorial-context",
    "GET /api/v1/public/experimental-spatial-history/{cutoff_date}", "GET /api/v1/public/metadata",
    "GET /api/v1/public/model-evaluation", "GET /api/v1/public/activity", "GET /api/v1/public/prevention",
    "GET /", "GET /health", "GET /health/ready", "POST /api/v1/admin/session",
}


def _dependencies(dependant, found):
    for dependency in dependant.dependencies:
        found.add(dependency.call)
        _dependencies(dependency, found)
    return found


def test_admin_routes_require_admin_role_and_public_surface_is_explicit(client):
    routes = {}
    for route in client.app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes[f"{method} {route.path}"] = get_current_admin in _dependencies(route.dependant, set())
    unguarded = {name for name, guarded in routes.items() if not guarded}
    assert unguarded == PUBLIC
    admin = [name for name in routes if name.split(" ", 1)[1].startswith("/api/v1/admin")]
    assert len(admin) >= 27 and all(routes[name] for name in admin if name != "POST /api/v1/admin/session")


def test_admin_routes_reject_missing_and_forged_tokens(client):
    checked = 0
    for route in client.app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/admin") and route.path != "/api/v1/admin/session":
            # Authentication runs before parameter validation, so a fictional placeholder suffices.
            path = "/".join("1" if part.startswith("{") else part for part in route.path.split("/"))
            for method in route.methods:
                for headers in ({}, {"Authorization": "Bearer forged.token.value"}):
                    response = client.request(method, path, headers=headers, json={})
                    assert response.status_code == 401, (method, path, response.status_code)
                    checked += 1
    assert checked >= 54
