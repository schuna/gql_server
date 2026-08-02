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


def test_create_or_get_returns_exact_existing_user_without_changing_password(
    user_service,
):
    service, hasher = user_service
    first = service.create_or_get(
        UserCreateSchema(
            username="alice", email="alice@example.com", password="one"
        )
    )
    duplicate = service.create_or_get(
        UserCreateSchema(
            username="alice", email="alice@example.com", password="different"
        )
    )

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.user.id == first.user.id
    assert service.get(first.user.id).password == "hashed:one"
    assert hasher.hashed_passwords == ["one"]
    assert len(service.list_users()) == 1


@pytest.mark.parametrize(
    ("username", "email"),
    [
        ("alice", "other@example.com"),
        ("other", "alice@example.com"),
    ],
)
def test_create_or_get_keeps_partial_unique_matches_as_conflicts(
    user_service, username, email
):
    service, _ = user_service
    service.create(
        UserCreateSchema(username="alice", email="alice@example.com", password="one")
    )

    with pytest.raises(ConflictError):
        service.create_or_get(
            UserCreateSchema(username=username, email=email, password="two")
        )


def test_create_or_get_keeps_cross_user_match_as_conflict(user_service):
    service, _ = user_service
    service.create(
        UserCreateSchema(username="alice", email="alice@example.com", password="one")
    )
    service.create(
        UserCreateSchema(username="bob", email="bob@example.com", password="two")
    )

    with pytest.raises(ConflictError):
        service.create_or_get(
            UserCreateSchema(
                username="alice", email="bob@example.com", password="three"
            )
        )


def test_create_or_get_requeries_after_insert_race(user_service, monkeypatch):
    service, _ = user_service
    strict_create = service.create

    def competing_insert(item):
        strict_create(item)
        raise ConflictError("Resource already exists")

    monkeypatch.setattr(service, "create", competing_insert)

    result = service.create_or_get(
        UserCreateSchema(
            username="alice", email="alice@example.com", password="one"
        )
    )

    assert result.created is False
    assert result.user.username == "alice"
    assert len(service.list_users()) == 1


def test_service_reports_missing_user(user_service):
    service, _ = user_service

    with pytest.raises(ResourceNotFoundError):
        service.get(999)
