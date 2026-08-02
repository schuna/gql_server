from contextlib import contextmanager
from typing import Iterator
import logging

from sqlalchemy import create_engine, orm, text
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from api.errors import DatabaseUnavailableError

logger = logging.getLogger(__name__)

Base = declarative_base()


class Database:

    def __init__(self, db_url: str) -> None:
        engine_options = {
            "echo": False,
            "pool_pre_ping": True,
        }
        if db_url.startswith("sqlite"):
            engine_options["connect_args"] = {
                "check_same_thread": False,
                "timeout": 5,
            }
        else:
            engine_options.update(
                {
                    "pool_recycle": 1800,
                    "pool_timeout": 5,
                }
            )
        self._engine = create_engine(db_url, **engine_options)
        self._session_factory = orm.scoped_session(
            orm.sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine,
            ),
        )

    def create_database(self) -> None:
        try:
            Base.metadata.create_all(self._engine)
        except Exception as exc:
            if self._is_connection_error(exc):
                raise DatabaseUnavailableError() from exc
            raise

    def ping(self) -> None:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            if self._is_connection_error(exc):
                raise DatabaseUnavailableError() from exc
            raise

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                OperationalError,
                InterfaceError,
                DisconnectionError,
                SQLAlchemyTimeoutError,
            ),
        ) or (isinstance(exc, DBAPIError) and exc.connection_invalidated)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session: Session = self._session_factory()
        try:
            yield session
        except Exception as exc:
            logger.exception("Session rollback because of exception")
            try:
                session.rollback()
            except Exception:
                logger.exception("Session rollback failed")
            if self._is_connection_error(exc):
                raise DatabaseUnavailableError() from exc
            raise
        finally:
            session.close()
