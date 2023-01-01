"""DAP exceptions.

These exceptions are mostly used by the server. When an exception is captured,
proper error message is displayed (according to the DAP 2.0 spec), with
information about the exception.

"""


class DapError(Exception):
    """Base DAP exception."""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class ClientError(DapError):
    """Generic error with the client."""


class ServerError(DapError):
    """Generic error with the server."""


class ConstraintExpressionError(ServerError):
    """Exception raised when an invalid constraint expression is given."""


class HandlerError(DapError):
    """Generic error with a handler."""


class ExtensionNotSupportedError(HandlerError):
    """Exception raised when opening a file not supported by any handlers."""


class OpenFileError(HandlerError):
    """Exception raised when unable to open a file."""
