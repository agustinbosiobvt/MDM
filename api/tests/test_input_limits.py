"""Every string the API accepts has a length limit (§7: Pydantic validation with length
limits on strings). Walks the request side of the OpenAPI schema: bodies, query and path
parameters, nested models, lists and dicts."""

from collections.abc import Iterator
from typing import Any

from app.main import create_app

BOUNDED_FORMATS = {"uuid", "date", "date-time", "binary", "email"}
# The upload itself: capped at UPLOAD_MAX_BYTES while streaming (test_import_security).
EXEMPT = {"POST /api/parties/{party_id}/imports body(multipart/form-data).file"}


def _resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref:
        node: Any = spec
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]
        return dict(node)
    return schema


def _unbounded(
    spec: dict[str, Any], schema: dict[str, Any], where: str, seen: set[str]
) -> Iterator[str]:
    ref = schema.get("$ref")
    if ref:
        if ref in seen:
            return
        seen = {*seen, ref}
    s = _resolve(spec, schema)
    for key in ("anyOf", "oneOf", "allOf"):
        for i, sub in enumerate(s.get(key, [])):
            yield from _unbounded(spec, sub, f"{where}[{key}{i}]", seen)
    if s.get("type") == "string" and not (
        "maxLength" in s or "enum" in s or "const" in s or s.get("format") in BOUNDED_FORMATS
    ):
        yield where
    for name, prop in s.get("properties", {}).items():
        yield from _unbounded(spec, prop, f"{where}.{name}", seen)
    if isinstance(s.get("items"), dict):
        yield from _unbounded(spec, s["items"], f"{where}[]", seen)
    if isinstance(s.get("additionalProperties"), dict):
        yield from _unbounded(spec, s["additionalProperties"], f"{where}{{}}", seen)
    if isinstance(s.get("propertyNames"), dict):
        yield from _unbounded(spec, s["propertyNames"], f"{where}{{key}}", seen)


def _request_inputs(spec: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            label = f"{method.upper()} {path}"
            for p in op.get("parameters", []):
                yield f"{label} {p['in']}:{p['name']}", p["schema"]
            for media, content in op.get("requestBody", {}).get("content", {}).items():
                yield f"{label} body({media})", content["schema"]


def test_every_request_string_is_length_limited() -> None:
    spec = create_app().openapi()
    inputs = list(_request_inputs(spec))
    assert len(inputs) > 50  # the walk really covers the API
    unbounded = [
        w
        for where, schema in inputs
        for w in _unbounded(spec, schema, where, set())
        if w not in EXEMPT
    ]
    assert unbounded == []
