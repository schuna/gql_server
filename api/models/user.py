from sqlalchemy import Column, Integer, String

from api.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True)
    email = Column(String(80), unique=True)
    password = Column(String(80))

