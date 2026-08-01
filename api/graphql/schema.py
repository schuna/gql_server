from typing import List, AsyncGenerator

# noinspection PyPackageRequirements
import strawberry
# noinspection PyPackageRequirements
from strawberry.file_uploads import Upload
from strawberry.types import Info

from api.graphql.fields import (
    UserSchema,
    FolderInput,
    UploadFileSchema,
    MessageSchema
)
from api.graphql.resolvers import (
    get_users,
    create_user,
    get_user,
    upload_file,
    get_messages,
    add_messages
)
from api.utils.auth import IsAuthenticated


@strawberry.type
class Query:
    user: UserSchema = strawberry.field(
        resolver=get_user,
        # permission_classes=[IsAuthenticated]
    )
    users: list[UserSchema] = strawberry.field(
        resolver=get_users,
        # permission_classes=[IsAuthenticated]
    )
    messages: List[MessageSchema] = strawberry.field(
        resolver=get_messages,
    )


@strawberry.type
class Mutation:
    user: UserSchema = strawberry.mutation(
        resolver=create_user,
        permission_classes=[IsAuthenticated]
    )

    read_file: UploadFileSchema = strawberry.mutation(
        resolver=upload_file,
        permission_classes=[IsAuthenticated]
    )

    messages: List[MessageSchema] = strawberry.mutation(
        resolver=add_messages,
        permission_classes=[IsAuthenticated]
    )

    @strawberry.mutation
    async def read_files(self, files: List[Upload]) -> List[str]:
        contents = []
        for file in files:
            content = (await file.read()).decode("utf-8")
            contents.append(content)
        return contents

    @strawberry.mutation
    async def read_folder(self, folder: FolderInput) -> List[str]:
        contents = []
        for file in folder.files:
            content = (await file.read()).decode("utf-8")
            contents.append(content)
        return contents


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def user_added_subscription(self, info: Info) -> AsyncGenerator[UserSchema, None]:
        import logging
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.info("starting add user")
        logger.info(id(info.context.broadcast))

        async with info.context.broadcast.subscribe(channel="add_user") as subscriber:
            logger.info(f"{subscriber}")
            async for event in subscriber:
                user = event.message
                logger.info(f"publish user: {UserSchema(**user)}")
                yield UserSchema(**user)

    @strawberry.subscription
    async def message_added_subscription(self, info: Info) -> AsyncGenerator[MessageSchema, None]:
        import logging
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.info("starting add message")
        logger.info(id(info.context.broadcast))

        async with info.context.broadcast.subscribe(channel="add_message") as subscriber:
            logger.info(f"sub: {subscriber}")
            async for event in subscriber:
                messages = event.message
                logger.info(f"publish: {len(messages)} messages")
                for message in messages:
                    yield message


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription
)
