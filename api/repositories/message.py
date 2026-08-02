from threading import Lock

from api.domain import Message


class MessageRepository:
    def __init__(self):
        self._messages: dict[int, list[Message]] = {}
        self._lock = Lock()

    def get_by_tid(self, tid: int, limit: int = 100) -> list[Message]:
        with self._lock:
            messages = self._messages.setdefault(tid, [])
            if limit < 1:
                return []
            return list(messages[-limit:])

    def get_max_id(self, tid: int) -> int:
        with self._lock:
            messages = self._messages.setdefault(tid, [])
            return messages[-1].id if messages else 0

    def add_by_tid(self, tid: int, messages: list[str]) -> list[Message]:
        with self._lock:
            buffer = self._messages.setdefault(tid, [])
            message_id = buffer[-1].id if buffer else 0
            entries = []
            for text in messages:
                message_id += 1
                entry = Message(id=message_id, tid=tid, text=text)
                buffer.append(entry)
                entries.append(entry)
            return entries
