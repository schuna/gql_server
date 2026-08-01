from sqlalchemy import Column, Integer, String, Text

from api.database import Base


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    tid = Column(Integer)
    text = Column(Text)

