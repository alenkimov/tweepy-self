from typing import Generator

from tenacity import AsyncRetrying, wait_fixed, stop_after_attempt
from requests.adapters import Retry

RETRIES = Retry(total=5, backoff_factor=0.9, status_forcelist=[500, 502, 503, 504])
ASYNC_RETRIES = AsyncRetrying(wait=wait_fixed(5), stop=stop_after_attempt(5), reraise=True)

REQUEST_URL = "https://api.capsolver.com"
VALID_STATUS_CODES = (200, 202, 400, 401, 405)

APP_ID = "6F895B2F-F454-44D1-8FE0-77ACAD3DBDC8"


# Connection retry generator
def attempts_generator(amount: int = 16) -> Generator:
    """
    Function generates a generator of length equal to `amount`

    Args:
        amount: number of attempts generated

    Yields:
        int: The next number in the range of 1 to ``amount`` - 1.

    Examples:
        Examples should be written in doctest format, and should illustrate how
        to use the function.

        >>> print([i for i in attempts_generator(5)])
        [1, 2, 3, 4]

    Returns:
        Attempt number
    """
    yield from range(1, amount)
