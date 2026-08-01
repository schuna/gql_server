import os
import time
import uuid
from pathlib import Path
from typing import List

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
# noinspection PyPackageRequirements
from strawberry.file_uploads import Upload
# noinspection PyPackageRequirements
from strawberry.types import Info

from api.graphql.fields import UserSchema, UserCreateInput, UploadFileSchema, MessageSchema
from api.schemas import UserCreateSchema
from api.utils.auth import Hash


async def get_users(info: Info) -> list[UserSchema]:
    return info.context.user_repository.gets().data


async def get_user(user_id: int, info: Info) -> UserSchema:
    return info.context.user_repository.get(user_id).data


async def create_user(data: UserCreateInput, info: Info) -> UserSchema:
    data.password = Hash.bcrypt(data.password)
    entry = UserCreateSchema(**data.__dict__)
    entry.password = Hash.bcrypt(entry.password)
    response = info.context.user_repository.add(entry)
    if response.success:
        await info.context.broadcast.publish(channel="add_user", message=jsonable_encoder(response.data))
        user_json = jsonable_encoder(response.data)
        print(f"user create: {user_json}")
        return response.data
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{response.message}")


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
