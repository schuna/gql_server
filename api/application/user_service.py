from collections.abc import Callable

from api.application.ports import UserUnitOfWorkPort
from api.domain import User
from api.errors import ResourceNotFoundError
from api.schemas import UserCreateSchema
from api.security import PasswordHasher


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
