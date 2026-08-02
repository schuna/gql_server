from contextlib import AbstractContextManager
from types import TracebackType
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.errors import ConflictError
from api.repositories.user import UserRepository


class SqlAlchemyUnitOfWork:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]],
    ) -> None:
        self._session_factory = session_factory
        self._session_context: AbstractContextManager[Session] | None = None
        self.session: Session | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session_context = self._session_factory()
        self.session = self._session_context.__enter__()
        self.users = UserRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session_context is not None:
            self._session_context.__exit__(exc_type, exc_value, traceback)
        self.session = None

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("Unit of work has not been entered")
        try:
            self.session.commit()
        except IntegrityError as exc:
            raise ConflictError("Resource already exists") from exc

    def rollback(self) -> None:
        if self.session is None:
            raise RuntimeError("Unit of work has not been entered")
        self.session.rollback()
