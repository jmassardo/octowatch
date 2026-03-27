"""Tests for global exception handlers and error schemas.

Tests cover:
- Global unhandled exception handler (500 catch-all)
- RequestValidationError handler (422 envelope)
- HTTPException handler (consistent error envelope)
- _status_to_code helper mapping
- ErrorResponse / ErrorBody / ErrorDetail schemas
- RequestIdMiddleware sets request.state.request_id
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import RequestIdMiddleware, _status_to_code
from app.schemas.error import ErrorBody, ErrorDetail, ErrorResponse

# ─── Test models ──────────────────────────────────────────────────────────────


class _ValidatedBody(BaseModel):
    """Pydantic model used to trigger RequestValidationError in tests."""

    name: str
    age: int


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_exception_app() -> FastAPI:
    """Build a minimal FastAPI app with all custom exception handlers registered.

    This mirrors the exception handler setup in create_app() without pulling in
    the full middleware stack, lifespan, or database dependencies.
    """
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    app = FastAPI()

    # Add RequestIdMiddleware so request.state.request_id is set
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. Please try again later.",
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": [
                        {
                            "field": ".".join(str(loc) for loc in err.get("loc", [])),
                            "message": err.get("msg", ""),
                            "type": err.get("type", ""),
                        }
                        for err in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": _status_to_code(exc.status_code),
                    "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                }
            },
            headers=getattr(exc, "headers", None),
        )

    # ── Test routes ───────────────────────────────────────────────────────────

    @app.get("/ok")
    async def ok_route() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/crash")
    async def crash_route() -> None:
        raise RuntimeError("something broke")

    @app.get("/not-found")
    async def not_found_route() -> None:
        raise HTTPException(status_code=404, detail="Resource not found")

    @app.get("/forbidden")
    async def forbidden_route() -> None:
        raise HTTPException(status_code=403, detail="Access denied")

    @app.get("/bad-request")
    async def bad_request_route() -> None:
        raise HTTPException(status_code=400, detail="Invalid input")

    @app.get("/conflict")
    async def conflict_route() -> None:
        raise HTTPException(status_code=409, detail="Resource already exists")

    @app.get("/service-unavailable")
    async def service_unavailable_route() -> None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    @app.get("/custom-status")
    async def custom_status_route() -> None:
        raise HTTPException(status_code=418, detail="I'm a teapot")

    @app.get("/http-error-dict-detail")
    async def http_error_dict_detail_route() -> None:
        raise HTTPException(status_code=400, detail={"key": "value"})

    @app.post("/validated")
    async def validated_route(payload: _ValidatedBody) -> dict[str, str]:
        return {"name": payload.name}

    return app


# ─── Unhandled exception handler ─────────────────────────────────────────────


class TestUnhandledExceptionHandler:
    def test_returns_500_status(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/crash")
        assert resp.status_code == 500

    def test_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/crash")
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "internal_error"

    def test_does_not_leak_stack_trace(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/crash")
        body = resp.json()
        assert "something broke" not in body["error"]["message"]
        assert "Traceback" not in body["error"]["message"]
        assert body["error"]["message"] == "An unexpected error occurred. Please try again later."

    def test_includes_request_id(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/crash")
        body = resp.json()
        request_id = body["error"]["request_id"]
        # RequestIdMiddleware should set a UUID-format request_id
        assert request_id != "unknown"
        assert len(request_id) == 36  # UUID format: 8-4-4-4-12

    def test_normal_route_not_affected(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ─── HTTPException handler ───────────────────────────────────────────────────


class TestHTTPExceptionHandler:
    def test_404_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Resource not found"

    def test_403_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/forbidden")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "forbidden"
        assert body["error"]["message"] == "Access denied"

    def test_400_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/bad-request")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "bad_request"
        assert body["error"]["message"] == "Invalid input"

    def test_409_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/conflict")
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "conflict"
        assert body["error"]["message"] == "Resource already exists"

    def test_503_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/service-unavailable")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "service_unavailable"
        assert body["error"]["message"] == "Service temporarily unavailable"

    def test_unmapped_status_uses_fallback_code(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/custom-status")
        assert resp.status_code == 418
        body = resp.json()
        assert body["error"]["code"] == "error_418"
        assert body["error"]["message"] == "I'm a teapot"

    def test_dict_detail_is_stringified(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/http-error-dict-detail")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "bad_request"
        # dict detail should be stringified
        assert isinstance(body["error"]["message"], str)

    def test_envelope_has_no_request_id(self) -> None:
        """HTTPException responses should not include request_id (only 500s do)."""
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.get("/not-found")
        body = resp.json()
        assert "request_id" not in body["error"]


# ─── Validation exception handler ────────────────────────────────────────────


class TestValidationExceptionHandler:
    def test_returns_422_for_invalid_body(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.post("/validated", json={"name": "Alice"})
        # missing required field "age"
        assert resp.status_code == 422

    def test_returns_error_envelope(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.post("/validated", json={"name": "Alice"})
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["message"] == "Request validation failed."

    def test_includes_field_details(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.post("/validated", json={"name": "Alice"})
        body = resp.json()
        details = body["error"]["details"]
        assert isinstance(details, list)
        assert len(details) >= 1
        # At least one detail should reference the "age" field
        age_errors = [d for d in details if "age" in d["field"]]
        assert len(age_errors) >= 1

    def test_detail_has_required_keys(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.post("/validated", json={"name": "Alice"})
        body = resp.json()
        for detail in body["error"]["details"]:
            assert "field" in detail
            assert "message" in detail
            assert "type" in detail

    def test_wrong_type_returns_422(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.post("/validated", json={"name": "Alice", "age": "not-a-number"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        details = body["error"]["details"]
        age_errors = [d for d in details if "age" in d["field"]]
        assert len(age_errors) >= 1

    def test_valid_body_passes(self) -> None:
        client = TestClient(_build_exception_app(), raise_server_exceptions=False)
        resp = client.post("/validated", json={"name": "Alice", "age": 30})
        assert resp.status_code == 200
        assert resp.json() == {"name": "Alice"}


# ─── _status_to_code helper ─────────────────────────────────────────────────


class TestStatusToCode:
    def test_maps_400(self) -> None:
        assert _status_to_code(400) == "bad_request"

    def test_maps_401(self) -> None:
        assert _status_to_code(401) == "unauthorized"

    def test_maps_403(self) -> None:
        assert _status_to_code(403) == "forbidden"

    def test_maps_404(self) -> None:
        assert _status_to_code(404) == "not_found"

    def test_maps_405(self) -> None:
        assert _status_to_code(405) == "method_not_allowed"

    def test_maps_409(self) -> None:
        assert _status_to_code(409) == "conflict"

    def test_maps_422(self) -> None:
        assert _status_to_code(422) == "validation_error"

    def test_maps_429(self) -> None:
        assert _status_to_code(429) == "rate_limited"

    def test_maps_500(self) -> None:
        assert _status_to_code(500) == "internal_error"

    def test_maps_503(self) -> None:
        assert _status_to_code(503) == "service_unavailable"

    def test_unmapped_code_uses_fallback(self) -> None:
        assert _status_to_code(418) == "error_418"

    def test_unmapped_code_502(self) -> None:
        assert _status_to_code(502) == "error_502"


# ─── RequestIdMiddleware ─────────────────────────────────────────────────────


class TestRequestIdMiddleware:
    def test_sets_x_request_id_header(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        @app.get("/test")
        async def test_route() -> dict[str, str]:
            return {"ok": "true"}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) == 36  # UUID

    def test_sets_request_state_request_id(self) -> None:
        """Verify request.state.request_id is set for use by exception handlers."""
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        captured_id: dict[str, str] = {}

        @app.get("/capture-id")
        async def capture_id_route(request: Request) -> dict[str, str]:
            captured_id["value"] = getattr(request.state, "request_id", "missing")
            return {"ok": "true"}

        client = TestClient(app)
        resp = client.get("/capture-id")
        assert resp.status_code == 200
        assert captured_id["value"] != "missing"
        assert len(captured_id["value"]) == 36  # UUID

    def test_request_id_matches_header(self) -> None:
        """The request.state.request_id should match the X-Request-ID header."""
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        captured_id: dict[str, str] = {}

        @app.get("/match-id")
        async def match_id_route(request: Request) -> dict[str, str]:
            captured_id["value"] = getattr(request.state, "request_id", "")
            return {"ok": "true"}

        client = TestClient(app)
        resp = client.get("/match-id")
        assert resp.headers["X-Request-ID"] == captured_id["value"]


# ─── Error schemas ───────────────────────────────────────────────────────────


class TestErrorSchemas:
    def test_error_detail_creation(self) -> None:
        detail = ErrorDetail(field="body.age", message="Field required", type="missing")
        assert detail.field == "body.age"
        assert detail.message == "Field required"
        assert detail.type == "missing"

    def test_error_body_minimal(self) -> None:
        body = ErrorBody(code="not_found", message="Resource not found")
        assert body.code == "not_found"
        assert body.message == "Resource not found"
        assert body.request_id is None
        assert body.details is None

    def test_error_body_with_request_id(self) -> None:
        body = ErrorBody(
            code="internal_error",
            message="An unexpected error occurred.",
            request_id="abc-123",
        )
        assert body.request_id == "abc-123"

    def test_error_body_with_details(self) -> None:
        detail = ErrorDetail(field="body.name", message="Required", type="missing")
        body = ErrorBody(
            code="validation_error",
            message="Request validation failed.",
            details=[detail],
        )
        assert body.details is not None
        assert len(body.details) == 1
        assert body.details[0].field == "body.name"

    def test_error_response_envelope(self) -> None:
        body = ErrorBody(code="not_found", message="Not found")
        envelope = ErrorResponse(error=body)
        assert envelope.error.code == "not_found"
        assert envelope.error.message == "Not found"

    def test_error_response_serialization(self) -> None:
        body = ErrorBody(
            code="validation_error",
            message="Request validation failed.",
            details=[
                ErrorDetail(field="body.age", message="Field required", type="missing"),
            ],
        )
        envelope = ErrorResponse(error=body)
        data = envelope.model_dump()
        assert data == {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "request_id": None,
                "details": [
                    {
                        "field": "body.age",
                        "message": "Field required",
                        "type": "missing",
                    }
                ],
            }
        }

    def test_error_response_json_excludes_none(self) -> None:
        body = ErrorBody(code="not_found", message="Not found")
        envelope = ErrorResponse(error=body)
        data = envelope.model_dump(exclude_none=True)
        assert "request_id" not in data["error"]
        assert "details" not in data["error"]
