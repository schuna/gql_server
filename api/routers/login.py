from datetime import timedelta

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
# noinspection PyPackageRequirements
from jose import jwt, JWTError

from api.application import UserService
from api.container import Container
from api.errors import ResourceNotFoundError
from api.schemas import UserCreateSchema, UserDisplaySchema
from api.graphql.fields import TokenSchema
from api.utils.auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, oauth2_scheme, SECRET_KEY, ALGORITHM

router = APIRouter(
    tags=["authentication"]
)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='Could not validate credentials',
    headers={"WWW-Authenticate": "Bearer"}
)


@inject
def get_current_user(
        token: str = Depends(oauth2_scheme),
        user_service: UserService = Depends(Provide[Container.user_service])):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        return user_service.get_by_username(username)
    except ResourceNotFoundError:
        raise credentials_exception


@router.post('/login', response_model=TokenSchema)
@inject
def login(
        request_form: OAuth2PasswordRequestForm = Depends(),
        user_service: UserService = Depends(Provide[Container.user_service])):
    user = user_service.authenticate(request_form.username, request_form.password)
    if user is None:
        raise credentials_exception

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(data={'username': user.username}, expires_delta=access_token_expires)
    return {
        'access_token': access_token,
        'token_type': 'bearer',
        'user_id': user.id,
        'username': user.username
    }


@router.post('/create_user', response_model=UserDisplaySchema)
@inject
def create_user(
        request: UserCreateSchema,
        user_service: UserService = Depends(Provide[Container.user_service])):
    return user_service.create(request)


@router.get("/get_user/{user_id}", response_model=UserDisplaySchema)
@inject
def get_user(
        user_id: int,
        user_service: UserService = Depends(Provide[Container.user_service])):
    return user_service.get(user_id)


@router.post("/update_user/{user_id}", response_model=UserDisplaySchema)
@inject
def update_user(user_id: int,
                request: UserCreateSchema,
                user_service: UserService = Depends(Provide[Container.user_service])):
    return user_service.update(user_id, request)


# noinspection PyUnusedLocal
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
def delete_user(user_id: int,
                user_service: UserService = Depends(Provide[Container.user_service]),
                current_user: UserDisplaySchema = Depends(get_current_user)):
    user_service.delete(user_id)
    return None
