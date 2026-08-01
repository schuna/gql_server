import os
import string
from datetime import timedelta, datetime
from typing import Optional, Any, Union, Awaitable

from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
# noinspection PyPackageRequirements
from jose import jwt, JWTError
from pydantic import ValidationError
# noinspection PyPackageRequirements
from strawberry.permission import BasePermission
# noinspection PyPackageRequirements
from strawberry.types import Info
# noinspection PyPackageRequirements
from starlette.requests import Request
# noinspection PyPackageRequirements
from starlette.websockets import WebSocket

from api.schemas import TokenPayload, TokenDataError

password_context = CryptContext(schemes='bcrypt', deprecated='auto')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = 'HS256'

ACCESS_TOKEN_EXPIRE_MINUTES = 525600


class Hash:
    @staticmethod
    def bcrypt(password: str):
        return password_context.hash(password)

    @staticmethod
    def verify(hashed_password, plain_password):
        return password_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_jwt(token: str, secret_key: str) -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)

        if datetime.fromtimestamp(token_data.exp) < datetime.now():
            return None

        return token_data
    except(JWTError, ValidationError):
        return None


def decode_access_token(token) -> Optional[TokenPayload]:
    return decode_jwt(token, SECRET_KEY)


class VerifyToken:
    def __init__(self, token):
        self.token = token

    def verify(self) -> Union[TokenPayload, TokenDataError]:
        token_data = decode_access_token(self.token)
        if token_data is None:
            return TokenDataError(status="error", message="Invalid token or expired token")

        return token_data


class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    async def has_permission(self, source: Any, info: Info, **kwargs) -> Union[bool, Awaitable[bool]]:
        request: Union[Request, WebSocket] = info.context.request
        if "authorization" in request.headers:
            result = VerifyToken(request.headers['authorization'][7:]).verify()
            if result.status != "error":
                return True

        return False


def generate_random_string(length: int = 32):
    letters = string.ascii_lowercase
    import random
    return ''.join(random.choice(letters) for _ in range(length))
