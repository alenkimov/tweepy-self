"""
Twitter API Wrapper
~~~~~~~~~~~~~~~~~~~

A basic wrapper for the Twitter user API.
"""

from ._twitter_client import Client
from ._account import Account, AccountStatus
from ._models import Tweet, UserData
from . import errors, utils

__all__ = [
    "Client",
    "Account",
    "AccountStatus",
    "utils",
    "errors",
]


import warnings
# HACK: Ignore event loop warnings from curl_cffi
warnings.filterwarnings('ignore', module='curl_cffi')
