import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.errors import ConflictError, DatabaseUnavailableError, ResourceNotFoundError


PUBLIC_DATABASE_ERROR = (
    "데이터 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found_handler(
        request: Request, exc: ResourceNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": str(exc),
                "code": exc.code,
                "request_id": get_request_id(request),
            },
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "code": exc.code,
                "request_id": get_request_id(request),
            },
        )

    @app.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_handler(
        request: Request, exc: DatabaseUnavailableError
    ) -> JSONResponse:
        request_id = get_request_id(request)
        return JSONResponse(
            status_code=503,
            media_type="application/problem+json",
            headers={"Retry-After": "3", "X-Request-ID": request_id},
            content={
                "type": "https://example.com/problems/database-unavailable",
                "title": "Service temporarily unavailable",
                "status": 503,
                "detail": PUBLIC_DATABASE_ERROR,
                "code": exc.code,
                "retryable": exc.retryable,
                "request_id": request_id,
            },
        )
