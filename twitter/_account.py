import enum

import pyotp

from .utils import hidden_value

# TODO Валидация
# AUTH_TOKEN_PATTERN = r"^[a-f0-9]{40}$"
# BACKUP_CODE_PATTERN = r"^[a-z0-9]{12}$"
# KEY_2FA_PATTERN = r"^[A-Z0-9]{16}$"


class AccountStatus(enum.StrEnum):
    BAD_TOKEN = "BAD_TOKEN"  # (401) 32
    UNKNOWN   = "UNKNOWN"
    SUSPENDED = "SUSPENDED"  # (403) 64, (200) 141
    LOCKED    = "LOCKED"     # (403) 326
    GOOD      = "GOOD"

    def __str__(self):
        return self.value


class Account:
    auth_token:  str | None
    ct0:         str | None
    id:          int | None
    name:        str | None
    username:    str | None
    password:    str | None
    email:       str | None
    key2fa:      str | None
    backup_code: str | None
    status: AccountStatus

    def __init__(
            self,
            auth_token:  str = None,
            *,
            username:    str = None,
            password:    str = None,
            email:       str = None,
            key2fa:      str = None,
            backup_code: str = None,
    ):
        self.auth_token  = auth_token
        self.ct0         = None
        self.id          = None
        self.name        = None
        self.username    = username
        self.password    = password
        self.email       = email
        self.key2fa      = key2fa
        self.backup_code = backup_code
        self.status      = AccountStatus.UNKNOWN

    @property
    def hidden_auth_token(self) -> str | None:
        return hidden_value(self.auth_token) if self.auth_token else None

    @property
    def hidden_password(self) -> str | None:
        return hidden_value(self.password) if self.password else None

    @property
    def hidden_key2fa(self) -> str | None:
        return hidden_value(self.key2fa) if self.key2fa else None

    @property
    def hidden_backup_code(self) -> str | None:
        return hidden_value(self.backup_code) if self.backup_code else None

    def __repr__(self):
        return f"{self.__class__.__name__}(auth_token={self.hidden_auth_token}, username={self.username})"

    def __str__(self):
        return self.hidden_auth_token

    def get_2fa_code(self) -> str | None:
        if not self.key2fa:
            raise ValueError("No key2fa")

        return str(pyotp.TOTP(self.key2fa).now())
