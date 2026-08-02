class ApplicationError(Exception):
    code = "APPLICATION_ERROR"


class ResourceNotFoundError(ApplicationError):
    code = "RESOURCE_NOT_FOUND"


class ConflictError(ApplicationError):
    code = "CONFLICT"


class DatabaseUnavailableError(ApplicationError):
    code = "DATABASE_UNAVAILABLE"

    def __init__(self, *, retryable: bool = True) -> None:
        self.retryable = retryable
        super().__init__("Database service is temporarily unavailable")


class BrokerUnavailableError(ApplicationError):
    code = "BROKER_UNAVAILABLE"

    def __init__(self, *, operation_committed: bool = False) -> None:
        self.operation_committed = operation_committed
        self.retryable = not operation_committed
        super().__init__("Message broker is temporarily unavailable")
