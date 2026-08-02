from api.models import User
from api.errors import ResourceNotFoundError
from api.repositories.base import RepositoryBase
from api.schemas import UserCreateSchema


class UserRepository(RepositoryBase[User, UserCreateSchema]):
    def __init__(self, session):
        super().__init__(User, session)

    def get_by_username(self, username: str) -> User:
        user = self.session.query(User).filter(User.username == username).first()
        if user is None:
            raise ResourceNotFoundError(f"User with name {username} not found")
        return user

    def list_users(self) -> list[User]:
        return self.list_items()
