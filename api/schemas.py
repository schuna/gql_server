from pydantic import BaseModel


class UserCreateSchema(BaseModel):
    username: str
    email: str
    password: str


class UserDisplaySchema(BaseModel):
    id: int
    username: str
    email: str
    password: str

    class Config:
        orm_mode = True


class TokenPayload(BaseModel):
    status: str = 'success'
    sub: str = None
    exp: int = None


class TokenDataError(BaseModel):
    status: str
    message: str


class MessageCreateSchema(BaseModel):
    tid: int
    text: str
