from dependency_injector.wiring import inject, Provide
from fastapi import Depends
# noinspection PyPackageRequirements
from strawberry.fastapi import BaseContext, GraphQLRouter
# noinspection PyPackageRequirements
from strawberry.subscriptions import GRAPHQL_TRANSPORT_WS_PROTOCOL, GRAPHQL_WS_PROTOCOL

from api.application import MessageService, UserService
from api.container import Container
from api.graphql.schema import schema
from api.messaging import EventBroker


class CustomContext(BaseContext):
    event_broker: EventBroker

    @inject
    def __init__(
            self,
            user_service: UserService = Depends(Provide[Container.user_service]),
            message_service: MessageService = Depends(Provide[Container.message_service]),
            event_broker: EventBroker = Depends(Provide[Container.event_broker])):
        super().__init__()
        self.message_service = message_service
        self.user_service = user_service
        self.event_broker = event_broker


def custom_context_dependency() -> CustomContext:
    return CustomContext()


async def get_context(custom_context=Depends(custom_context_dependency), ):
    return custom_context


graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    multipart_uploads_enabled=True,
    subscription_protocols=[
        GRAPHQL_TRANSPORT_WS_PROTOCOL, GRAPHQL_WS_PROTOCOL
    ]
)
