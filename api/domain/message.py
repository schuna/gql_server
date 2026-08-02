from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    id: int
    tid: int
    text: str
