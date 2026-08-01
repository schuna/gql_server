from api.models import User
from api.repositories.base import RepositoryBase, V, T
from api.graphql.fields import ResponseSchema


class UserRepository(RepositoryBase[T, V]):

    def get_by_username(self, username: str) -> ResponseSchema:
        with self.session_factory() as session:
            user = session.query(User).filter(User.username.like(username)).first()
            if not user:
                return ResponseSchema(**{"success": False, "message": f"User with name {username} not found"})
            else:
                return ResponseSchema(**{"data": user})
