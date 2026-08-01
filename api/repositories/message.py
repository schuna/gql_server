from typing import List

from api.graphql.fields import ResponseSchema, MessageSchema

message_buffer = dict()


class MessageRepository:
    def __init__(self):
        self.pid = 1

    def get_by_tid(self, tid: int, limit: int = 100) -> ResponseSchema:
        if f"tid{tid}" not in message_buffer.keys():
            message_buffer[f"tid{tid}"] = []
        message_buffer[f"tid{tid}"] = message_buffer[f"tid{tid}"][-limit:]
        return ResponseSchema(**{"data": message_buffer[f"tid{tid}"]})

    def get_max_id(self, tid: int) -> int:
        if f"tid{tid}" not in message_buffer.keys():
            message_buffer[f"tid{tid}"] = []
        if message_buffer[f"tid{tid}"]:
            return message_buffer[f"tid{tid}"][-1].id
        else:
            return 0

    def add_by_tid(self, tid: int, messages: List[str]) -> ResponseSchema:
        entries = []
        m_id = self.get_max_id(tid)
        for message in messages:
            m_id += 1
            entry = MessageSchema(**{
                "id": m_id,
                "tid": tid,
                "text": message
            })
            message_buffer[f"tid{tid}"].append(entry)
            entries.append(entry)
        return ResponseSchema(**{"data": entries})
