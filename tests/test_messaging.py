import asyncio

from broadcaster import Broadcast

from api.domain import Message
from api.errors import BrokerUnavailableError
from api.messaging import EventBroker


class FailingBackend:
    async def connect(self):
        raise ConnectionError("broker down")


def test_event_broker_translates_backend_connection_errors():
    broker = EventBroker(FailingBackend())

    try:
        asyncio.run(broker.connect())
    except BrokerUnavailableError as exc:
        assert exc.retryable is True
        assert exc.operation_committed is False
        assert isinstance(exc.__cause__, ConnectionError)
        assert broker.connected is False
    else:
        raise AssertionError("BrokerUnavailableError was not raised")


def test_event_broker_serializes_structured_payloads():
    async def round_trip():
        broker = EventBroker(Broadcast("memory://"))
        await broker.connect()
        try:
            async with broker.subscribe("messages") as subscriber:
                await broker.publish(
                    "messages",
                    [Message(id=1, tid=7, text="hello")],
                )
                event = await subscriber.__anext__()
                return event.message
        finally:
            await broker.disconnect()

    assert asyncio.run(round_trip()) == [
        {"id": 1, "tid": 7, "text": "hello"}
    ]
