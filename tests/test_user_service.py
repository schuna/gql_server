import pytest

from api.application import UserService
from api.database import Database
from api.domain import User
from api.errors import ConflictError, ResourceNotFoundError
from api.schemas import UserCreateSchema
from api.unit_of_work import SqlAlchemyUnitOfWork


class RecordingPasswordHasher:
    def __init__(self):
        self.hashed_passwords = []

    def hash(self, password):
        self.hashed_passwords.append(password)
        return f"hashed:{password}"

    def verify(self, password, hashed_password):
        return hashed_password == f"hashed:{password}"


@pytest.fixture
def user_service():
    database = Database("sqlite:///:memory:")
    database.create_database()
    hasher = RecordingPasswordHasher()
    service = UserService(
        uow_factory=lambda: SqlAlchemyUnitOfWork(database.session),
        password_hasher=hasher,
    )
    return service, hasher


def test_service_owns_hashing_and_transaction(user_service):
    service, hasher = user_service
    request = UserCreateSchema(
        username="alice",
        email="alice@example.com",
        password="plain-password",
    )

    created = service.create(request)
    loaded = service.get(created.id)

    assert hasher.hashed_passwords == ["plain-password"]
    assert isinstance(created, User)
    assert not hasattr(created, "_sa_instance_state")
    assert request.password == "plain-password"
    assert loaded.password == "hashed:plain-password"
    assert service.authenticate("alice", "plain-password").id == created.id
    assert service.authenticate("alice", "wrong-password") is None


def test_unit_of_work_rolls_back_conflicting_user(user_service):
    service, _ = user_service
    service.create(
        UserCreateSchema(username="alice", email="alice@example.com", password="one")
    )

    with pytest.raises(ConflictError):
        service.create(
            UserCreateSchema(
                username="alice",
                email="other@example.com",
                password="two",
            )
        )

    assert [user.username for user in service.list_users()] == ["alice"]


def test_service_reports_missing_user(user_service):
    service, _ = user_service

    with pytest.raises(ResourceNotFoundError):
        service.get(999)
