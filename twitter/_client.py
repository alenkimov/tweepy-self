from ._session import BaseAsyncSession


class BaseClient:
    _DEFAULT_HEADERS = None

    def __init__(self, **session_kwargs):
        self._session = BaseAsyncSession(
            headers=session_kwargs.pop("headers", None) or self._DEFAULT_HEADERS,
            **session_kwargs,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.close()

    def close(self):
        self._session.close()
