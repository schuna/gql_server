import uuid

from graphql import GraphQLError
from strawberry.types import Info

from api.error_handlers import PUBLIC_BROKER_ERROR, PUBLIC_DATABASE_ERROR
from api.errors import (
    BrokerUnavailableError,
    ConflictError,
    DatabaseUnavailableError,
    ResourceNotFoundError,
)


def database_unavailable_graphql_error(
    info: Info, exc: DatabaseUnavailableError
) -> GraphQLError:
    request = getattr(info.context, "request", None)
    request_id = getattr(
        getattr(request, "state", None), "request_id", str(uuid.uuid4())
    )
    return GraphQLError(
        PUBLIC_DATABASE_ERROR,
        extensions={
            "code": exc.code,
            "retryable": exc.retryable,
            "request_id": request_id,
        },
    )


def conflict_graphql_error(exc: ConflictError) -> GraphQLError:
    return GraphQLError(str(exc), extensions={"code": exc.code, "retryable": False})


def resource_not_found_graphql_error(exc: ResourceNotFoundError) -> GraphQLError:
    return GraphQLError(str(exc), extensions={"code": exc.code, "retryable": False})


def broker_unavailable_graphql_error(
    info: Info, exc: BrokerUnavailableError
) -> GraphQLError:
    request = getattr(info.context, "request", None)
    request_id = getattr(
        getattr(request, "state", None), "request_id", str(uuid.uuid4())
    )
    return GraphQLError(
        PUBLIC_BROKER_ERROR,
        extensions={
            "code": exc.code,
            "retryable": exc.retryable,
            "operation_committed": exc.operation_committed,
            "request_id": request_id,
        },
    )
