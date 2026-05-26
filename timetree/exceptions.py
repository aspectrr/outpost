class TimeTreeError(Exception):
    """Base exception for TimeTree API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(TimeTreeError):
    """Authentication failure (400 / 401 / 403)."""


class NotFoundError(TimeTreeError):
    """Resource not found (404)."""


class RateLimitError(TimeTreeError):
    """Rate limited (429)."""
