"""Dokumentasi API untuk developer (INTERFACE.md §6.1): setiap operasi di
/openapi.json punya role minimum, deskripsi, dan skema error; endpoint inti
punya contoh request/response."""

from __future__ import annotations

import pytest

from api.openapi_docs import DOCS


@pytest.fixture(scope="module")
def schema():
    from api.main import app
    app.openapi_schema = None
    return app.openapi()


def _ops(schema):
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                yield method, path, op


def test_every_operation_documented(schema):
    missing = [(m, p) for m, p, op in _ops(schema)
               if not op.get("x-min-role") or "Minimum role" not in op.get("description", "")]
    assert not missing, missing


def test_error_schema_referenced(schema):
    assert set(schema["components"]["schemas"]["ErrorResponse"]["required"]) == {"detail", "code"}
    op = schema["paths"]["/api/disasters"]["post"]
    assert op["responses"]["403"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert "TOKEN_WRITE_FORBIDDEN" in op["description"]


def test_curated_docs_point_to_real_operations(schema):
    for method, path in DOCS:
        assert method.lower() in schema["paths"].get(path, {}), (method, path)


def test_core_examples_present(schema):
    body = schema["paths"]["/api/disasters"]["post"]["requestBody"]["content"]["application/json"]
    assert body["example"]["disaster_type_code"] == "BANJIR"
    today = schema["paths"]["/api/hydromet/today"]["get"]["responses"]["200"]["content"]["application/json"]
    assert today["example"]["regions"][0]["bmkg_category"] == "LEBAT"
    assert schema["paths"]["/api/hydromet/observations"]["get"]["x-min-role"] == "USER"
