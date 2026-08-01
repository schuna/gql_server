import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from api.container import Container
import api.routers.login as login_endpoint
from api.routers.graphql import graphql_router
import api.routers.file as file_endpoint
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
container = Container()
db = container.db()
db.create_database()

app = FastAPI()
app.container = container
app.include_router(file_endpoint.router)
app.include_router(login_endpoint.router)
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
