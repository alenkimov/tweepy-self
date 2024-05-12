from curl_cffi import requests

from .account import Account

__all__ = [
    "TwitterException",
    "FailedToFindDuplicatePost",
    "HTTPException",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "RateLimited",
    "ServerError",
    "BadAccount",
    "BadAccountToken",
    "AccountLocked",
    "AccountConsentLocked",
    "AccountSuspended",
    "AccountNotFound",
]


class TwitterException(Exception):
    pass


class FailedToFindDuplicatePost(TwitterException):
    pass


def _http_exception_message(
    response: requests.Response,
    api_errors: list[dict],
    detail: str | None,
    custom_exception_message: str = None,
):
    exception_message = f"(response status: {response.status_code})"
    if custom_exception_message:
        exception_message += f" {custom_exception_message}"
    if detail:
        exception_message += f"\n(detail) {detail}"
    for error in api_errors:
        if "code" in error and "message" in error:
            exception_message += f"\n(code {error['code']}) {error['message']}"
        elif "message" in error:
            exception_message += f"\n{error['message']}"
    return exception_message


class HTTPException(TwitterException):
    """Exception raised when an HTTP request fails."""

    def __init__(
        self,
        response: requests.Response,
        data: dict | str,
        custom_exception_message: str = None,
    ):
        self.response = response
        self.api_errors: list[dict] = []
        self.api_codes: list[int] = []
        self.api_messages: list[str] = []
        self.detail: str | None = None
        self.html: str | None = None

        # Если ответ — строка, то это html
        if isinstance(data, str):
            if not data:
                exception_message = (
                    f"(response status: {response.status_code}) Empty response body."
                )
            else:
                self.html = data
                exception_message = f"(response status: {response.status_code}) HTML Response:\n{self.html}"
            if response.status_code == 429:
                exception_message = (
                    f"(response status: {response.status_code}) Rate limit exceeded."
                    f" Set wait_on_rate_limit=True to ignore this exception."
                )
            super().__init__(exception_message)
            return

        self.api_errors = data.get("errors", [data])
        self.detail = data.get("detail")

        for error in self.api_errors:
            if "code" in error:
                self.api_codes.append(error["code"])
            if "message" in error:
                self.api_messages.append(error["message"])

        exception_message = _http_exception_message(
            response, self.api_errors, self.detail, custom_exception_message
        )
        super().__init__(exception_message)


class BadRequest(HTTPException):
    """Exception raised for a 400 HTTP status code."""

    pass


class Unauthorized(HTTPException):
    """Exception raised for a 401 HTTP status code."""

    pass


class Forbidden(HTTPException):
    """Exception raised for a 403 HTTP status code."""

    pass


class NotFound(HTTPException):
    """Exception raised for a 404 HTTP status code."""

    pass


class RateLimited(HTTPException):
    """Exception raised for a 429 HTTP status code."""

    pass


class ServerError(HTTPException):
    """Exception raised for a 5xx HTTP status code."""

    pass


class BadAccount(TwitterException):
    def __init__(
        self,
        http_exception: "HTTPException",
        account: Account,
        custom_exception_message: str = None,
    ):
        self.http_exception = http_exception
        self.account = account
        exception_message = _http_exception_message(
            http_exception.response,
            http_exception.api_errors,
            http_exception.detail,
            custom_exception_message or "Bad Twitter account.",
        )
        super().__init__(exception_message)


class BadAccountToken(BadAccount):
    def __init__(self, http_exception: "HTTPException", account: Account):
        exception_message = (
            "Bad Twitter account's auth_token. Relogin to get new token."
        )
        super().__init__(http_exception, account, exception_message)


class AccountLocked(BadAccount):
    def __init__(self, http_exception: "HTTPException", account: Account):
        exception_message = (
            f"Twitter account is locked."
            f" Set CapSolver API key (capsolver_api_key) to auto-unlock."
        )
        super().__init__(http_exception, account, exception_message)


class AccountConsentLocked(BadAccount):
    def __init__(self, http_exception: "HTTPException", account: Account):
        exception_message = f"Twitter account is locked."
        super().__init__(http_exception, account, exception_message)


class AccountSuspended(BadAccount):
    def __init__(self, http_exception: "HTTPException", account: Account):
        exception_message = f"Twitter account is suspended."
        super().__init__(http_exception, account, exception_message)


class AccountNotFound(BadAccount):
    def __init__(self, http_exception: "HTTPException", account: Account):
        exception_message = f"Twitter account not found or deleted."
        super().__init__(http_exception, account, exception_message)
