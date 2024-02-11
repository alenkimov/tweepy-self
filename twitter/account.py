from pathlib import Path
from typing import Sequence, Iterable
import enum

from pydantic import BaseModel, Field
import pyotp

from .utils import hidden_value, load_lines, write_lines


class AccountStatus(enum.StrEnum):
    UNKNOWN        = "UNKNOWN"
    BAD_TOKEN      = "BAD_TOKEN"
    SUSPENDED      = "SUSPENDED"
    LOCKED         = "LOCKED"
    CONSENT_LOCKED = "CONSENT_LOCKED"
    GOOD           = "GOOD"

    def __str__(self):
        return self.value


class Account(BaseModel):
    auth_token:  str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    ct0:         str | None = None
    id:          int | None = None
    name:        str | None = None
    username:    str | None = None
    password:    str | None = None
    email:       str | None = None
    totp_secret: str | None = None
    backup_code: str | None = None
    status: AccountStatus = AccountStatus.UNKNOWN

    @property
    def hidden_auth_token(self) -> str | None:
        return hidden_value(self.auth_token) if self.auth_token else None

    @property
    def hidden_password(self) -> str | None:
        return hidden_value(self.password) if self.password else None

    @property
    def hidden_totp_secret(self) -> str | None:
        return hidden_value(self.totp_secret) if self.totp_secret else None

    @property
    def hidden_backup_code(self) -> str | None:
        return hidden_value(self.backup_code) if self.backup_code else None

    def __repr__(self):
        return f"{self.__class__.__name__}(auth_token={self.hidden_auth_token}, username={self.username})"

    def __str__(self):
        return self.hidden_auth_token

    def get_totp_code(self) -> str | None:
        if not self.totp_secret:
            raise ValueError("No key2fa")

        return str(pyotp.TOTP(self.totp_secret).now())


def load_accounts_from_file(
        filepath: Path | str,
        *,
        separator: str = ":",
        fields: Sequence[str] = ("auth_token", "password", "email", "username"),
) -> list[Account]:
    """
    :param filepath: Путь до файла с данными об аккаунтах.
    :param separator: Разделитель между данными в строке.
    :param fields: Кортеж, содержащий имена полей в порядке их появления в строке.
    :return: Список Twitter аккаунтов.
    """
    accounts = []
    for line in load_lines(filepath):
        data = dict(zip(fields, line.split(separator)))
        data.update({key: None for key in data if not data[key]})
        accounts.append(Account(**data))
    return accounts


def extract_accounts_to_file(
        filepath: Path | str,
        accounts: Iterable[Account],
        *,
        separator: str = ":",
        fields: Sequence[str] = ("auth_token", "password", "email", "username"),
):
    lines = []
    for account in accounts:
        account_data = []
        for field_name in fields:
            field = getattr(account, field_name)
            field = field if field is not None else ""
            account_data.append(field)
        lines.append(separator.join(account_data))
    write_lines(filepath, lines)
