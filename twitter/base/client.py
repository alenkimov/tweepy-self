from .session import BaseAsyncSession


class BaseHTTPClient:
    _DEFAULT_HEADERS = None

    def __init__(self, **session_kwargs):
        self._session = BaseAsyncSession(
            headers=session_kwargs.pop("headers", None) or self._DEFAULT_HEADERS,
            **session_kwargs,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        await self._session.close()
