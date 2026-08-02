from dependency_injector import containers, providers

from api.application import UserService
from api.database import Database
from api.repositories.message import MessageRepository
from api.security import PasswordHasher
from api.unit_of_work import SqlAlchemyUnitOfWork


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=[
        "api.routers.login",
        "api.routers.graphql",
        "api.routers.health",
    ])
    config = providers.Configuration(yaml_files=["config.yml"])
    db = providers.Singleton(Database, db_url=config.db.url)
    password_hasher = providers.Singleton(PasswordHasher)
    unit_of_work = providers.Factory(
        SqlAlchemyUnitOfWork,
        session_factory=db.provided.session,
    )
    user_service = providers.Factory(
        UserService,
        uow_factory=unit_of_work.provider,
        password_hasher=password_hasher,
    )
    message_repository = providers.Factory(
        MessageRepository
    )

