import json

from fastapi import FastAPI
from fastapi.routing import APIWebSocketRoute
from fastapi.testclient import TestClient

from api.graphql.schema import schema
from api.routers.graphql import graphql_router


def test_schema_builds_with_expected_operations():
    schema_definition = schema.as_str()

    assert "type Query" in schema_definition
    assert "type Mutation" in schema_definition
    assert "type Subscription" in schema_definition
    assert "userAddedSubscription" in schema_definition
    assert "messageAddedSubscription" in schema_definition


def test_schema_executes_a_smoke_query():
    result = schema.execute_sync("{ __typename }")

    assert result.errors is None
    assert result.data == {"__typename": "Query"}


def test_router_supports_uploads_and_websockets():
    assert graphql_router.multipart_uploads_enabled is True
    assert any(isinstance(route, APIWebSocketRoute) for route in graphql_router.routes)


def test_router_serves_http_and_multipart_uploads():
    app = FastAPI()
    app.include_router(graphql_router, prefix="/graphql")

    websocket_routes = [
        route
        for route in app.routes
        if isinstance(route, APIWebSocketRoute) and route.path == "/graphql"
    ]
    assert len(websocket_routes) == 1

    with TestClient(app) as client:
        response = client.post("/graphql", json={"query": "{ __typename }"})
        assert response.status_code == 200
        assert response.json() == {"data": {"__typename": "Query"}}

        operations = {
            "query": "mutation($files: [Upload!]!) { readFiles(files: $files) }",
            "variables": {"files": [None]},
        }
        file_map = {"0": ["variables.files.0"]}
        response = client.post(
            "/graphql",
            data={
                "operations": json.dumps(operations),
                "map": json.dumps(file_map),
            },
            files={"0": ("hello.txt", b"hello", "text/plain")},
        )

        assert response.status_code == 200
        assert response.json() == {"data": {"readFiles": ["hello"]}}
