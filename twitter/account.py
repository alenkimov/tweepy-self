import enum

from pydantic import BaseModel, Field
import pyotp

from .utils import hidden_value


class AccountStatus(enum.StrEnum):
    BAD_TOKEN = "BAD_TOKEN"  # (401) 32
    UNKNOWN   = "UNKNOWN"
    SUSPENDED = "SUSPENDED"  # (403) 64, (200) 141
    LOCKED    = "LOCKED"     # (403) 326
    GOOD      = "GOOD"

    def __str__(self):
        return self.value


class Account(BaseModel):
    auth_token:  str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    ct0:         str | None
    id:          int | None
    name:        str | None
    username:    str | None
    password:    str | None
    email:       str | None
    key2fa:      str | None = Field(default=None, pattern=r"^[a-f0-9]{12}$")
    backup_code: str | None = Field(default=None, pattern=r"^[A-Z0-9]{16}$")
    status: AccountStatus = AccountStatus.UNKNOWN

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
