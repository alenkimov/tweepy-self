"""
Twitter API Wrapper
~~~~~~~~~~~~~~~~~~~

A basic wrapper for the Twitter user API.
"""

from .client import Client
from .account import Account, AccountStatus, load_accounts_from_file, extract_accounts_to_file
from .models import Tweet, UserData
from . import errors, utils

__all__ = [
    "Client",
    "Account",
    "AccountStatus",
    "utils",
    "errors",
    "load_accounts_from_file",
    "extract_accounts_to_file",
]


import warnings
# HACK: Ignore event loop warnings from curl_cffi
warnings.filterwarnings('ignore', module='curl_cffi')


from python3_capsolver.core import config
config.APP_ID = "6F895B2F-F454-44D1-8FE0-77ACAD3DBDC8"
