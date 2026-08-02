from collections.abc import Callable
from dataclasses import dataclass

from api.application.ports import UserUnitOfWorkPort
from api.domain import User
from api.errors import ConflictError, ResourceNotFoundError
from api.schemas import UserCreateSchema
from api.security import PasswordHasher


@dataclass(frozen=True)
class CreateUserResult:
    user: User
    created: bool


class UserService:
    def __init__(
        self,
        uow_factory: Callable[[], UserUnitOfWorkPort],
        password_hasher: PasswordHasher,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher

    def authenticate(self, username: str, password: str) -> User | None:
        try:
            user = self.get_by_username(username)
        except ResourceNotFoundError:
            return None
        if not self._password_hasher.verify(password, user.password):
            return None
        return user

    def create(self, item: UserCreateSchema) -> User:
        secured_item = UserCreateSchema(
            username=item.username,
            email=item.email,
            password=self._password_hasher.hash(item.password),
        )
        with self._uow_factory() as uow:
            user = uow.users.add(secured_item)
            uow.commit()
            return user

    def create_or_get(self, item: UserCreateSchema) -> CreateUserResult:
        """Create a user, or return the exact existing username/email match.

        A match on only one unique field remains a conflict: returning that user
        would silently accept input that identifies a different account.
        """
        with self._uow_factory() as uow:
            existing = self._resolve_existing(
                uow.users.find_by_username_or_email(item.username, item.email),
                item,
            )
            if existing is not None:
                return CreateUserResult(user=existing, created=False)

        try:
            return CreateUserResult(user=self.create(item), created=True)
        except ConflictError:
            # Another transaction may have inserted the same user after the
            # initial lookup. The failed session has exited and rolled back;
            # use a fresh unit of work before querying again.
            with self._uow_factory() as uow:
                existing = self._resolve_existing(
                    uow.users.find_by_username_or_email(item.username, item.email),
                    item,
                )
                if existing is not None:
                    return CreateUserResult(user=existing, created=False)
            raise

    @staticmethod
    def _resolve_existing(
        matches: list[User], item: UserCreateSchema
    ) -> User | None:
        exact_matches = [
            user
            for user in matches
            if user.username == item.username and user.email == item.email
        ]
        if len(matches) == 1 and len(exact_matches) == 1:
            return exact_matches[0]
        if matches:
            raise ConflictError("Resource already exists")
        return None

    def get(self, user_id: int) -> User:
        with self._uow_factory() as uow:
            return uow.users.get(user_id)

    def list_users(self) -> list[User]:
        with self._uow_factory() as uow:
            return uow.users.list_users()

    def get_by_username(self, username: str) -> User:
        with self._uow_factory() as uow:
            return uow.users.get_by_username(username)

    def update(self, user_id: int, item: UserCreateSchema) -> User:
        secured_item = UserCreateSchema(
            username=item.username,
            email=item.email,
            password=self._password_hasher.hash(item.password),
        )
        with self._uow_factory() as uow:
            user = uow.users.update(user_id, secured_item)
            uow.commit()
            return user

    def delete(self, user_id: int) -> None:
        with self._uow_factory() as uow:
            uow.users.delete(user_id)
            uow.commit()
