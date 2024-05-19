"""
Twitter API Wrapper
~~~~~~~~~~~~~~~~~~~

A Python library for interacting with the Twitter API.
"""

from .client import Client
from .account import (
    Account,
    AccountStatus,
    load_accounts_from_file,
    extract_accounts_to_file,
)
from .models import Tweet, User, Media, Image
from . import errors, utils

__all__ = [
    "Client",
    "Account",
    "AccountStatus",
    "Tweet",
    "User",
    "Media",
    "Image",
    "utils",
    "errors",
    "load_accounts_from_file",
    "extract_accounts_to_file",
]


import warnings

# HACK: Ignore event loop warnings from curl_cffi
warnings.filterwarnings("ignore", module="curl_cffi")

from loguru import logger

logger.disable("twitter")
