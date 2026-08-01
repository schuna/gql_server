from datetime import timedelta

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
# noinspection PyPackageRequirements
from jose import jwt, JWTError

from api.container import Container
from api.models import User
from api.repositories.user import UserRepository
from api.schemas import UserCreateSchema, UserDisplaySchema
from api.graphql.fields import TokenSchema
from api.utils.auth import (
    Hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, oauth2_scheme, SECRET_KEY, ALGORITHM
)

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
        user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository])):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    response = user_repository.get_by_username(username)

    if not response.success:
        raise credentials_exception

    return response.data


@router.post('/login', response_model=TokenSchema)
@inject
def login(
        request_form: OAuth2PasswordRequestForm = Depends(),
        user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository])):
    user_response = user_repository.get_by_username(request_form.username)
    if not user_response.success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid credentials")
    user = user_response.data
    if not Hash.verify(user.password, request_form.password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid credentials")

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
        user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository])):
    request.password = Hash.bcrypt(request.password)
    response = user_repository.add(request)
    if response.success:
        return response.data
    else:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{response.message}")


@router.get("/get_user/{id}", response_model=UserDisplaySchema)
@inject
def get_user(
        user_id: int,
        user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository])):
    response = user_repository.get(user_id)
    if response.success:
        return response.data
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{response.message}")


@router.post("/update_user/{user_id}", response_model=UserDisplaySchema)
@inject
def update_user(user_id: int,
                request: UserCreateSchema,
                user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository])):
    request.password = Hash.bcrypt(request.password)
    response = user_repository.update(user_id, request)
    if response.success:
        return response.data
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{response.message}")


# noinspection PyUnusedLocal
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
def delete_user(user_id: int,
                user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository]),
                current_user: UserDisplaySchema = Depends(get_current_user)):
    response = user_repository.delete(user_id)
    if response.success:
        return response.data
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{response.message}")
