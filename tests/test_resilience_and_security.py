import asyncio
from types import SimpleNamespace

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from api.database import Database
from api.error_handlers import PUBLIC_DATABASE_ERROR, register_exception_handlers
from api.errors import DatabaseUnavailableError
from api.graphql.fields import UserCreateInput
from api.graphql.resolvers import create_user
from api.middleware import RequestIdMiddleware
from api.routers.health import liveness, readiness


class FailingEngine:
    def connect(self):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


class FakeUserService:
    def __init__(self):
        self.entry = None

    def create(self, entry):
        self.entry = entry
        return SimpleNamespace(
            id=1,
            username=entry.username,
            email=entry.email,
        )


class FakeBroadcast:
    def __init__(self):
        self.message = None

    async def publish(self, **kwargs):
        self.message = kwargs["message"]
        return None


def test_database_ping_and_connection_error_translation():
    database = Database("sqlite:///:memory:")
    database.ping()

    database._engine = FailingEngine()
    try:
        database.ping()
    except DatabaseUnavailableError as exc:
        assert exc.retryable is True
        assert isinstance(exc.__cause__, OperationalError)
    else:
        raise AssertionError("DatabaseUnavailableError was not raised")


def test_rest_database_error_is_safe_and_retryable():
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/fails")
    def fails():
        raise DatabaseUnavailableError()

    with TestClient(app) as client:
        response = client.get("/fails", headers={"X-Request-ID": "request-123"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "3"
    assert response.headers["X-Request-ID"] == "request-123"
    assert response.json() == {
        "type": "https://example.com/problems/database-unavailable",
        "title": "Service temporarily unavailable",
        "status": 503,
        "detail": PUBLIC_DATABASE_ERROR,
        "code": "DATABASE_UNAVAILABLE",
        "retryable": True,
        "request_id": "request-123",
    }


def test_health_checks_distinguish_live_from_ready():
    assert liveness() == {"status": "ok"}

    class UnavailableDatabase:
        def ping(self):
            raise DatabaseUnavailableError()

    response = Response()
    result = readiness(response=response, database=UnavailableDatabase())

    assert response.status_code == 503
    assert result == {"status": "unavailable", "database": "unavailable"}


def test_graphql_schema_does_not_expose_password():
    from api.graphql.schema import schema

    user_output = schema.as_str().split("type UserSchema {", 1)[1].split("}", 1)[0]
    assert "password" not in user_output


def test_graphql_database_error_has_stable_extensions():
    from api.graphql.schema import schema

    class UnavailableService:
        def list_users(self):
            raise DatabaseUnavailableError()

    request = SimpleNamespace(state=SimpleNamespace(request_id="graphql-request"))
    context = SimpleNamespace(
        request=request,
        user_service=UnavailableService(),
    )
    result = asyncio.run(schema.execute("{ users { id } }", context_value=context))

    assert result.data is None
    assert len(result.errors) == 1
    assert result.errors[0].message == PUBLIC_DATABASE_ERROR
    assert result.errors[0].extensions == {
        "code": "DATABASE_UNAVAILABLE",
        "retryable": True,
        "request_id": "graphql-request",
    }


def test_graphql_user_creation_uses_service_and_public_event():
    service = FakeUserService()
    broadcast = FakeBroadcast()
    info = SimpleNamespace(
        context=SimpleNamespace(
            user_service=service,
            broadcast=broadcast,
        )
    )

    result = asyncio.run(
        create_user(
            UserCreateInput(
                username="test-user",
                email="test@example.com",
                password="plain-password",
            ),
            info,
        )
    )

    assert service.entry.password == "plain-password"
    assert result.username == "test-user"
    assert broadcast.message == {
        "id": 1,
        "username": "test-user",
        "email": "test@example.com",
    }
