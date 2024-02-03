from curl_cffi import requests

from ._account import Account

__all__ = [
    "TwitterException",
    "HTTPException",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "RateLimited",
    "ServerError",
    "BadAccount",
    "BadToken",
    "Locked",
    "Suspended",
]


class TwitterException(Exception):
    pass


class BadAccount(TwitterException):
    def __init__(
            self,
            account: Account,
            custom_exception_message: str = None,
    ):
        self.account = account
        exception_message = f"Bad Twitter account."
        super().__init__(custom_exception_message or exception_message)


class BadToken(BadAccount):
    def __init__(self, account: Account):
        exception_message = f"Bad Twitter account's auth_token."
        super().__init__(account, custom_exception_message=exception_message)


class Locked(BadAccount):
    def __init__(self, account: Account):
        exception_message = f"Twitter account is locked. Captcha required to unlock."
        super().__init__(account, custom_exception_message=exception_message)


class Suspended(BadAccount):
    def __init__(self, account: Account):
        exception_message = f"Twitter account is suspended."
        super().__init__(account, custom_exception_message=exception_message)


class HTTPException(TwitterException):
    """Exception raised when an HTTP request fails.
    """

    def __init__(
            self,
            response: requests.Response,
            data: dict | str,
            custom_exception_message: str = None,
    ):
        self.response = response
        self.api_errors: list[dict[str, int | str]] = []
        self.api_codes: list[int] = []
        self.api_messages: list[str] = []

        # Если ответ — строка, то это html
        if isinstance(data, str):
            exception_message = f"{response.status_code}"
            if response.status_code == 429:
                exception_message = (f"{response.status_code} Rate limit exceeded."
                                     f"\nSet twitter.Client(wait_on_rate_limit=True) to ignore this exception.")
            super().__init__(exception_message)
            return

        errors = data.get("errors", [])

        if "error" in data:
            errors.append(data["error"])
        else:
            errors.append(data)

        error_text = ""

        for error in errors:
            self.api_errors.append(error)

            if isinstance(error, str):
                self.api_messages.append(error)
                error_text += '\n' + error
                continue

            if "code" in error:
                self.api_codes.append(error["code"])
            if "message" in error:
                self.api_messages.append(error["message"])

            if "code" in error and "message" in error:
                error_text += f"\n{error['code']} - {error['message']}"
            elif "message" in error:
                error_text += '\n' + error["message"]

        if not error_text and "detail" in data:
            self.api_messages.append(data["detail"])
            error_text = '\n' + data["detail"]
        exception_message = f"{response.status_code} {error_text}"
        super().__init__(custom_exception_message or exception_message)


class BadRequest(HTTPException):
    """Exception raised for a 400 HTTP status code.
    """
    pass


class Unauthorized(HTTPException):
    """Exception raised for a 401 HTTP status code.
    """
    pass


class Forbidden(HTTPException):
    """Exception raised for a 403 HTTP status code.
    """
    pass


class NotFound(HTTPException):
    """Exception raised for a 404 HTTP status code.
    """
    pass


class RateLimited(HTTPException):
    """Exception raised for a 429 HTTP status code.
    """
    pass


class ServerError(HTTPException):
    """Exception raised for a 5xx HTTP status code.
    """
    pass
