"""Authorization is enforced on the server for every endpoint.

1. Every /api route declares a minimum role (a new unprotected route fails here).
2. The role matrix: anonymous → 401, a lower role → 403, the minimum role or higher → allowed.
"""

import re
import uuid
from collections.abc import Callable, Iterable, Iterator

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.auth.deps import ROLE_RANK
from app.main import create_app
from app.users.models import Role
from tests.conftest import LoggedIn

PUBLIC = {("GET", "/api/health")}


def _min_role(dependant: Dependant) -> Role | None:
    for dep in dependant.dependencies:
        role = getattr(dep.call, "min_role", None)
        if role is not None:
            return Role(role)
        nested = _min_role(dep)
        if nested is not None:
            return nested
    return None


def _walk(routes: Iterable[object]) -> Iterator[APIRoute]:
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        # FastAPI wraps include_router() lazily; descend into the original router.
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _walk(inner.routes)


def _api_routes() -> Iterator[tuple[str, str, Role | None]]:
    for route in _walk(create_app().routes):
        if route.path.startswith("/api"):
            for method in sorted(route.methods or ()):
                yield method, route.path, _min_role(route.dependant)


ROUTES = [r for r in _api_routes() if (r[0], r[1]) not in PUBLIC]


def test_there_are_protected_routes() -> None:
    assert len(ROUTES) >= 6


@pytest.mark.parametrize(("method", "path", "role"), ROUTES, ids=lambda v: str(v))
def test_every_api_route_requires_a_role(method: str, path: str, role: Role | None) -> None:
    assert role is not None, f"{method} {path} has no Require* dependency"


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def _call(client: TestClient, method: str, path: str, csrf: str = "") -> int:
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    body: dict[str, object] | None = {} if method in {"POST", "PUT", "PATCH"} else None
    return client.request(method, _concrete(path), json=body, headers=headers).status_code


@pytest.mark.parametrize(("method", "path", "role"), ROUTES, ids=lambda v: str(v))
def test_anonymous_gets_401(client: TestClient, method: str, path: str, role: Role) -> None:
    assert _call(client, method, path) == 401


@pytest.mark.parametrize("user_role", list(Role))
@pytest.mark.parametrize(("method", "path", "role"), ROUTES, ids=lambda v: str(v))
def test_role_matrix(
    client: TestClient,
    login: Callable[..., LoggedIn],
    user_role: Role,
    method: str,
    path: str,
    role: Role,
) -> None:
    me = login(f"{user_role.value}@buenavidatrading.com", role=user_role.value)
    status = _call(client, method, path, me.csrf)
    if ROLE_RANK[user_role] < ROLE_RANK[role]:
        assert status == 403, f"{user_role} should be refused on {method} {path}"
    else:
        assert status not in (401, 403), f"{user_role} should be allowed on {method} {path}"


@pytest.mark.parametrize(("method", "path", "role"), [r for r in ROUTES if r[0] != "GET"])
def test_state_changing_routes_need_csrf_token(
    client: TestClient, login: Callable[..., LoggedIn], method: str, path: str, role: Role
) -> None:
    login("admin@buenavidatrading.com", role="admin")
    assert _call(client, method, path, csrf="") == 403
