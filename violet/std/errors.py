from violet.errors import RuntimeException

__all__ = (
    "RuntimeException",
    "ValueException"
)

class ValueException(RuntimeException):
    pass

class ArgumentException(RuntimeException):
    pass