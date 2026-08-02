from api.application import MessageService
from api.repositories.message import MessageRepository


def test_message_service_generates_and_reads_messages():
    repository = MessageRepository()
    service = MessageService(repository)

    first_batch = service.add_generated_messages(tid=7, count=3)
    second_batch = service.add_generated_messages(tid=7, count=2)

    assert [(message.id, message.text) for message in first_batch] == [
        (1, "1"),
        (2, "2"),
        (3, "3"),
    ]
    assert [(message.id, message.text) for message in second_batch] == [
        (4, "4"),
        (5, "5"),
    ]
    assert [message.id for message in service.get_messages(7, limit=2)] == [4, 5]


def test_message_repository_state_is_instance_scoped():
    first = MessageService(MessageRepository())
    second = MessageService(MessageRepository())

    first.add_generated_messages(tid=1, count=1)

    assert len(first.get_messages(1)) == 1
    assert second.get_messages(1) == []
