import asyncio

from dependency_injector import providers
from fastapi.testclient import TestClient

import main


class FakeDatabase:
    def __init__(self):
        self.created = False

    def create_database(self):
        self.created = True


class FakeEventBroker:
    def __init__(self):
        self.connected = False
        self.disconnected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True


def test_lifespan_owns_database_startup_and_broadcast_lifecycle():
    database = FakeDatabase()
    event_broker = FakeEventBroker()

    async def run_lifespan():
        main.container.db.override(providers.Object(database))
        main.container.event_broker.override(providers.Object(event_broker))
        try:
            async with main.lifespan(main.app):
                assert database.created is True
                assert event_broker.connected is True
                assert event_broker.disconnected is False
        finally:
            main.container.event_broker.reset_override()
            main.container.db.reset_override()

    asyncio.run(run_lifespan())

    assert event_broker.disconnected is True


def test_main_app_uses_managed_dependencies_for_graphql():
    database = FakeDatabase()
    event_broker = FakeEventBroker()
    main.container.db.override(providers.Object(database))
    main.container.event_broker.override(providers.Object(event_broker))
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/graphql",
                json={"query": "{ messages(tid: 99) { id tid text } }"},
            )
            assert response.status_code == 200
            assert response.json() == {"data": {"messages": []}}
            assert event_broker.connected is True
    finally:
        main.container.event_broker.reset_override()
        main.container.db.reset_override()

    assert database.created is True
    assert event_broker.disconnected is True
