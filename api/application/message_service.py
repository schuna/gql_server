from api.application.ports import MessageRepositoryPort
from api.domain import Message


class MessageService:
    def __init__(self, repository: MessageRepositoryPort) -> None:
        self._repository = repository

    def get_messages(self, tid: int, limit: int = 100) -> list[Message]:
        return self._repository.get_by_tid(tid, limit)

    def add_generated_messages(self, tid: int, count: int = 100) -> list[Message]:
        last_id = self._repository.get_max_id(tid)
        texts = [str(last_id + offset) for offset in range(1, count + 1)]
        return self._repository.add_by_tid(tid, texts)
