import asyncio
from types import SimpleNamespace

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from api.database import Database
from api.application import CreateUserResult
from api.error_handlers import PUBLIC_DATABASE_ERROR, register_exception_handlers
from api.errors import BrokerUnavailableError, DatabaseUnavailableError
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

    def create_or_get(self, entry):
        self.entry = entry
        return CreateUserResult(
            user=SimpleNamespace(
                id=1,
                username=entry.username,
                email=entry.email,
            ),
            created=True,
        )


class FakeEventBroker:
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
    event_broker = SimpleNamespace(connected=False)
    result = readiness(
        response=response,
        database=UnavailableDatabase(),
        event_broker=event_broker,
    )

    assert response.status_code == 503
    assert result == {
        "status": "unavailable",
        "database": "unavailable",
        "broker": "unavailable",
    }

    class AvailableDatabase:
        def ping(self):
            return None

    response = Response()
    result = readiness(
        response=response,
        database=AvailableDatabase(),
        event_broker=event_broker,
    )
    assert response.status_code == 503
    assert result == {
        "status": "unavailable",
        "database": "available",
        "broker": "unavailable",
    }


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
    event_broker = FakeEventBroker()
    info = SimpleNamespace(
        context=SimpleNamespace(
            user_service=service,
            event_broker=event_broker,
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
    assert event_broker.message == {
        "id": 1,
        "username": "test-user",
        "email": "test@example.com",
    }


def test_graphql_reports_committed_operation_when_publish_fails():
    class UserService:
        def create_or_get(self, entry):
            return CreateUserResult(
                user=SimpleNamespace(
                    id=1, username=entry.username, email=entry.email
                ),
                created=True,
            )

    class FailingEventBroker:
        async def publish(self, **kwargs):
            raise BrokerUnavailableError()

    request = SimpleNamespace(state=SimpleNamespace(request_id="broker-request"))
    info = SimpleNamespace(
        context=SimpleNamespace(
            request=request,
            user_service=UserService(),
            event_broker=FailingEventBroker(),
        )
    )

    try:
        asyncio.run(
            create_user(
                UserCreateInput(
                    username="test-user",
                    email="test@example.com",
                    password="plain-password",
                ),
                info,
            )
        )
    except Exception as exc:
        assert exc.extensions == {
            "code": "BROKER_UNAVAILABLE",
            "retryable": False,
            "operation_committed": True,
            "request_id": "broker-request",
        }
    else:
        raise AssertionError("Broker error was not exposed")


def test_graphql_duplicate_user_does_not_publish_event():
    class ExistingUserService:
        def create_or_get(self, entry):
            return CreateUserResult(
                user=SimpleNamespace(
                    id=1, username=entry.username, email=entry.email
                ),
                created=False,
            )

    class UnexpectedEventBroker:
        async def publish(self, **kwargs):
            raise AssertionError("Duplicate user must not publish add_user")

    info = SimpleNamespace(
        context=SimpleNamespace(
            user_service=ExistingUserService(),
            event_broker=UnexpectedEventBroker(),
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

    assert result.id == 1
