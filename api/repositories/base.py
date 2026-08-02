from typing import TypeVar, Generic, Type

from sqlalchemy.orm import Session

from api.errors import ResourceNotFoundError

T = TypeVar("T")
V = TypeVar("V")


class RepositoryBase(Generic[T, V]):
    def __init__(self, model: Type[T], session: Session) -> None:
        self.model = model
        self.session = session

    # Create
    def add(self, item: V) -> T:
        entry = self.model(**item.dict())
        self.session.add(entry)
        return entry

    # Read
    def get(self, item_id: int) -> T:
        entry = self.session.query(self.model).get(item_id)
        if entry is None:
            raise ResourceNotFoundError(
                f"{self.model.__name__} with id {item_id} not found"
            )
        return entry

    def list_items(self) -> list[T]:
        return self.session.query(self.model).all()

    # Update
    def update(self, item_id: int, item: V) -> T:
        entry = self.get(item_id)
        for field, value in item.dict().items():
            setattr(entry, field, value)
        return entry

    # Delete
    def delete(self, item_id: int) -> None:
        entry = self.get(item_id)
        self.session.delete(entry)
