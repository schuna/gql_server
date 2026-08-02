from api.domain import User
from api.errors import ConflictError, ResourceNotFoundError
from api.models import UserRecord
from api.schemas import UserCreateSchema
from sqlalchemy.exc import IntegrityError


class UserRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _to_domain(record: UserRecord) -> User:
        return User(
            id=record.id,
            username=record.username,
            email=record.email,
            password=record.password,
        )

    def add(self, item: UserCreateSchema) -> User:
        record = UserRecord(**item.dict())
        self.session.add(record)
        self._flush()
        return self._to_domain(record)

    def get(self, user_id: int) -> User:
        record = self.session.query(UserRecord).get(user_id)
        if record is None:
            raise ResourceNotFoundError(f"User with id {user_id} not found")
        return self._to_domain(record)

    def get_by_username(self, username: str) -> User:
        record = (
            self.session.query(UserRecord)
            .filter(UserRecord.username == username)
            .first()
        )
        if record is None:
            raise ResourceNotFoundError(f"User with name {username} not found")
        return self._to_domain(record)

    def list_users(self) -> list[User]:
        records = self.session.query(UserRecord).all()
        return [self._to_domain(record) for record in records]

    def update(self, user_id: int, item: UserCreateSchema) -> User:
        record = self.session.query(UserRecord).get(user_id)
        if record is None:
            raise ResourceNotFoundError(f"User with id {user_id} not found")
        for field, value in item.dict().items():
            setattr(record, field, value)
        self._flush()
        return self._to_domain(record)

    def delete(self, user_id: int) -> None:
        record = self.session.query(UserRecord).get(user_id)
        if record is None:
            raise ResourceNotFoundError(f"User with id {user_id} not found")
        self.session.delete(record)

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("Resource already exists") from exc
