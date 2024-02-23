from datetime import datetime

from pydantic import BaseModel

from .utils import to_datetime


class UserData(BaseModel):
    id: int
    username: str
    name: str
    created_at: datetime
    description: str
    location: str
    followers_count: int
    friends_count: int
    raw_data: dict

    def __str__(self):
        return f"({self.id}) @{self.username}"

    @classmethod
    def from_raw_user_data(cls, data: dict):
        legacy = data["legacy"]
        keys = ("name", "description", "location", "followers_count", "friends_count")
        values = {key: legacy[key] for key in keys}
        values.update(
            {
                "id": int(data["rest_id"]),
                "username": legacy["screen_name"],
                "created_at": to_datetime(legacy["created_at"]),
                "raw_data": data,
            }
        )
        return cls(**values)


class Tweet(BaseModel):
    user_id: int
    id: int
    created_at: datetime
    full_text: str
    lang: str
    favorite_count: int
    quote_count: int
    reply_count: int
    retweet_count: int
    retweeted: bool
    raw_data: dict
    url: str | None = None

    def __str__(self):
        short_text = (
            f"{self.full_text[:32]}..." if len(self.full_text) > 16 else self.full_text
        )
        return f"({self.id}) {short_text}"

    @classmethod
    def from_raw_data(cls, data: dict):
        legacy = data["legacy"]
        keys = (
            "full_text",
            "lang",
            "favorite_count",
            "quote_count",
            "reply_count",
            "retweet_count",
            "retweeted",
        )
        values = {key: legacy[key] for key in keys}
        values.update(
            {
                "user_id": int(legacy["user_id_str"]),
                "id": int(legacy["id_str"]),
                "created_at": to_datetime(legacy["created_at"]),
                "raw_data": data,
            }
        )
        return cls(**values)
