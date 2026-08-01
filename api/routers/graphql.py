from broadcaster import Broadcast
from dependency_injector.wiring import inject, Provide
from fastapi import Depends
# noinspection PyPackageRequirements
from strawberry.fastapi import BaseContext, GraphQLRouter
# noinspection PyPackageRequirements
from strawberry.subscriptions import GRAPHQL_TRANSPORT_WS_PROTOCOL, GRAPHQL_WS_PROTOCOL

from api.container import Container
from api.graphql.schema import schema
from api.models import User
from api.models.message import Message
from api.repositories.message import MessageRepository
from api.repositories.user import UserRepository
from api.schemas import UserCreateSchema, MessageCreateSchema


class CustomContext(BaseContext):
    broadcast: Broadcast

    @inject
    def __init__(
            self,
            user_repository: UserRepository[User, UserCreateSchema] = Depends(Provide[Container.user_repository]),
            message_repository: MessageRepository = Depends(Provide[Container.message_repository])):
        super().__init__()
        self.message_repository = message_repository
        self.user_repository = user_repository


broadcast = None


async def get_broadcast():
    global broadcast
    if not broadcast:
        broadcast = Broadcast("memory://")
        await broadcast.connect()
    return broadcast


def custom_context_dependency() -> CustomContext:
    return CustomContext()


async def get_context(custom_context=Depends(custom_context_dependency), ):
    custom_context.broadcast = await get_broadcast()
    return custom_context


graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    subscription_protocols=[
        GRAPHQL_TRANSPORT_WS_PROTOCOL, GRAPHQL_WS_PROTOCOL
    ]
)
