from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response, status

from api.container import Container
from api.database import Database
from api.errors import DatabaseUnavailableError
from api.messaging import EventBroker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
@inject
def readiness(
    response: Response,
    database: Database = Depends(Provide[Container.db]),
    event_broker: EventBroker = Depends(Provide[Container.event_broker]),
) -> dict[str, str]:
    try:
        database.ping()
    except DatabaseUnavailableError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unavailable",
            "database": "unavailable",
            "broker": "available" if event_broker.connected else "unavailable",
        }
    if not event_broker.connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unavailable",
            "database": "available",
            "broker": "unavailable",
        }
    return {"status": "ready", "database": "available", "broker": "available"}
