import asyncio

from dependency_injector import providers
from fastapi.testclient import TestClient

import main


class FakeDatabase:
    def __init__(self):
        self.created = False

    def create_database(self):
        self.created = True


class FakeBroadcast:
    def __init__(self):
        self.connected = False
        self.disconnected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True


def test_lifespan_owns_database_startup_and_broadcast_lifecycle():
    database = FakeDatabase()
    broadcast = FakeBroadcast()

    async def run_lifespan():
        main.container.db.override(providers.Object(database))
        main.container.broadcast.override(providers.Object(broadcast))
        try:
            async with main.lifespan(main.app):
                assert database.created is True
                assert broadcast.connected is True
                assert broadcast.disconnected is False
        finally:
            main.container.broadcast.reset_override()
            main.container.db.reset_override()

    asyncio.run(run_lifespan())

    assert broadcast.disconnected is True


def test_main_app_uses_managed_dependencies_for_graphql():
    database = FakeDatabase()
    broadcast = FakeBroadcast()
    main.container.db.override(providers.Object(database))
    main.container.broadcast.override(providers.Object(broadcast))
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/graphql",
                json={"query": "{ messages(tid: 99) { id tid text } }"},
            )
            assert response.status_code == 200
            assert response.json() == {"data": {"messages": []}}
            assert broadcast.connected is True
    finally:
        main.container.broadcast.reset_override()
        main.container.db.reset_override()

    assert database.created is True
    assert broadcast.disconnected is True
