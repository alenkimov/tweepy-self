import enum


class AccountStatus(enum.StrEnum):
    UNKNOWN = "UNKNOWN"
    BAD_TOKEN = "BAD_TOKEN"
    SUSPENDED = "SUSPENDED"
    LOCKED = "LOCKED"
    CONSENT_LOCKED = "CONSENT_LOCKED"
    GOOD = "GOOD"

    def __str__(self):
        return self.value
