import logging
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from api.container import Container
from api.error_handlers import register_exception_handlers
from api.errors import DatabaseUnavailableError
from api.middleware import RequestIdMiddleware
import api.routers.login as login_endpoint
import api.routers.health as health_endpoint
from api.routers.graphql import graphql_router
import api.routers.file as file_endpoint
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
container = Container()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        container.db().create_database()
    except DatabaseUnavailableError:
        logger.exception("Database is unavailable during startup; readiness is degraded")
    yield


app = FastAPI(lifespan=lifespan)
app.container = container
register_exception_handlers(app)
app.add_middleware(RequestIdMiddleware)
app.include_router(file_endpoint.router)
app.include_router(login_endpoint.router)
app.include_router(health_endpoint.router)
app.include_router(graphql_router, prefix="/graphql")

origins = [
    'http://localhost:3000',
    'http://localhost:3001'
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=['*']
)


def serve():
    uvicorn.run(app, host="localhost", port=8000)


if __name__ == '__main__':
    serve()
