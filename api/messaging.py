import json
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from broadcaster import Broadcast

from api.errors import BrokerUnavailableError


@dataclass(frozen=True)
class BrokerEvent:
    message: Any


class EventSubscriber:
    def __init__(self, subscriber) -> None:
        self._iterator = subscriber.__aiter__()

    def __aiter__(self):
        return self

    async def __anext__(self) -> BrokerEvent:
        event = await self._iterator.__anext__()
        message = event.message
        if isinstance(message, (str, bytes, bytearray)):
            message = json.loads(message)
        return BrokerEvent(message=message)


class EventBroker:
    def __init__(self, backend: Broadcast) -> None:
        self._backend = backend
        self.connected = False

    async def connect(self) -> None:
        try:
            await self._backend.connect()
            self.connected = True
        except Exception as exc:
            self.connected = False
            raise BrokerUnavailableError() from exc

    async def disconnect(self) -> None:
        try:
            await self._backend.disconnect()
        except Exception as exc:
            raise BrokerUnavailableError() from exc
        finally:
            self.connected = False

    async def publish(self, channel: str, message) -> None:
        if not self.connected:
            raise BrokerUnavailableError()
        try:
            payload = json.dumps(message, default=self._serialize)
            await self._backend.publish(channel=channel, message=payload)
        except Exception as exc:
            if isinstance(exc, BrokerUnavailableError):
                raise
            raise BrokerUnavailableError() from exc

    @asynccontextmanager
    async def subscribe(self, channel: str):
        if not self.connected:
            raise BrokerUnavailableError()
        try:
            async with self._backend.subscribe(channel=channel) as subscriber:
                yield EventSubscriber(subscriber)
        except BrokerUnavailableError:
            raise
        except Exception as exc:
            raise BrokerUnavailableError() from exc

    @staticmethod
    def _serialize(value):
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"Unsupported broker payload type: {type(value).__name__}")
