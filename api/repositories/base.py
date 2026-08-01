import logging
from contextlib import AbstractContextManager
from typing import Callable, TypeVar, Generic, Type

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.graphql.fields import ResponseSchema

T = TypeVar("T")
V = TypeVar("V")


class RepositoryBase(Generic[T, V]):
    def __init__(self,
                 model: Type[T],
                 session_factory: Callable[..., AbstractContextManager[Session]]) -> None:
        self.model = model
        self.session_factory = session_factory

    # Create
    def add(self, item: V) -> ResponseSchema:
        with self.session_factory() as session:
            try:
                entry = self.model(**item.dict())
                session.add(entry)
                session.commit()
                session.refresh(entry)
                return ResponseSchema(**{"data": entry})
            except IntegrityError:
                logging.info("Duplicated Error")
                session.rollback()
                return ResponseSchema(**{"success": False, "message": f"Duplicated Error {item.json()}"})

    # Read
    def get(self, item_id: int) -> ResponseSchema:
        with self.session_factory() as session:
            entry = session.query(self.model).get(item_id)
            if not entry:
                return ResponseSchema(**{"success": False, "message": f"User with id {item_id} not found"})
            else:
                return ResponseSchema(**{"data": entry})

    def gets(self) -> ResponseSchema:
        with self.session_factory() as session:
            return ResponseSchema(**{"data": session.query(self.model).all()})

    # Update
    def update(self, item_id: int, item: V) -> ResponseSchema:
        with self.session_factory() as session:
            entries = session.query(self.model).filter(self.model.id == item_id)
            if not entries.first():
                return ResponseSchema(**{"success": False, "message": f"User with id {item_id} not found"})
            entries.update(item.dict())
            session.commit()
            session.refresh(entries.first())
            return ResponseSchema(**{"data": entries.first()})

    # Delete
    def delete(self, item_id: int) -> ResponseSchema:
        with self.session_factory() as session:
            entry = session.query(self.model).get(item_id)
            if not entry:
                return ResponseSchema(**{"success": False, "message": f"User with id {item_id} not found"})
            session.delete(entry)
            session.commit()
            return ResponseSchema()
