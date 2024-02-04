"""
Twitter API Wrapper
~~~~~~~~~~~~~~~~~~~

A basic wrapper for the Twitter user API.
"""

from .client import Client
from .account import Account, AccountStatus
from .models import Tweet, UserData
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
