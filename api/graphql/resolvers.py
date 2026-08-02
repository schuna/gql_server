import os
import uuid
from pathlib import Path
from typing import List

# noinspection PyPackageRequirements
from strawberry.file_uploads import Upload
# noinspection PyPackageRequirements
from strawberry.types import Info

from api.graphql.fields import UserSchema, UserCreateInput, UploadFileSchema, MessageSchema
from api.errors import ConflictError, DatabaseUnavailableError, ResourceNotFoundError
from api.graphql.errors import (
    conflict_graphql_error,
    database_unavailable_graphql_error,
    resource_not_found_graphql_error,
)
from api.schemas import UserCreateSchema


async def get_users(info: Info) -> list[UserSchema]:
    try:
        return info.context.user_service.list_users()
    except DatabaseUnavailableError as exc:
        raise database_unavailable_graphql_error(info, exc) from exc


async def get_user(user_id: int, info: Info) -> UserSchema:
    try:
        return info.context.user_service.get(user_id)
    except ResourceNotFoundError as exc:
        raise resource_not_found_graphql_error(exc) from exc
    except DatabaseUnavailableError as exc:
        raise database_unavailable_graphql_error(info, exc) from exc


async def create_user(data: UserCreateInput, info: Info) -> UserSchema:
    entry = UserCreateSchema(**data.__dict__)
    try:
        user = info.context.user_service.create(entry)
    except ConflictError as exc:
        raise conflict_graphql_error(exc) from exc
    except DatabaseUnavailableError as exc:
        raise database_unavailable_graphql_error(info, exc) from exc
    public_user = {"id": user.id, "username": user.username, "email": user.email}
    await info.context.broadcast.publish(channel="add_user", message=public_user)
    return user


async def upload_file(filename: str, file: Upload):
    upload_dir = Path("asset")
    content = await file.read()
    filename = f"{str(uuid.uuid4())}_{filename}"

    with open(os.path.join(upload_dir, filename), "wb") as fp:
        fp.write(content)

    return UploadFileSchema(**{"filename": filename})


async def get_messages(tid: int, info: Info) -> List[MessageSchema]:
    return info.context.message_repository.get_by_tid(tid).data


async def add_messages(tid: int, info: Info) -> List[MessageSchema]:
    id_max = info.context.message_repository.get_max_id(tid)
    data = [f'{id_max + x + 1}' for x in range(100)]
    response = info.context.message_repository.add_by_tid(tid=tid, messages=data)
    await info.context.broadcast.publish(channel="add_message", message=response.data)
    return response.data
