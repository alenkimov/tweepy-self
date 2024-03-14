from datetime import datetime, timedelta

from pydantic import BaseModel

from .utils import to_datetime


class Image(BaseModel):
    type: str
    width: int
    height: int


class Media(BaseModel):
    id: int
    image: Image
    size: int
    expires_at: datetime

    def __str__(self):
        return str(self.id)

    @classmethod
    def from_raw_data(cls, data: dict):
        expires_at = datetime.now() + timedelta(seconds=data["expires_after_secs"])
        values = {
            "image": {
                "type": data["image"]["image_type"],
                "width": data["image"]["w"],
                "height": data["image"]["h"],
            },
            "size": data["size"],
            "id": data["media_id"],
            "expires_at": expires_at,
        }
        return cls(**values)


class User(BaseModel):
    # fmt: off
    id:              int      | None = None
    username:        str      | None = None
    name:            str      | None = None
    created_at:      datetime | None = None
    description:     str      | None = None
    location:        str      | None = None
    followers_count: int      | None = None
    friends_count:   int      | None = None
    raw_data:        dict     | None = None
    # fmt: on

    def __str__(self):
        return str(self.id)

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, username={self.username})"

    @classmethod
    def from_raw_data(cls, data: dict):
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
    id: int
    user_id: int
    created_at: datetime
    text: str
    lang: str
    favorite_count: int
    quote_count: int
    reply_count: int
    retweet_count: int
    retweeted: bool
    raw_data: dict
    url: str | None = None

    def __str__(self):
        return str(self.id)

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, user_id={self.user_id})"

    @property
    def short_text(self) -> str:
        return f"{self.text[:32]}..." if len(self.text) > 16 else self.text

    @classmethod
    def from_raw_data(cls, data: dict):
        legacy = data["legacy"]
        keys = (
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
                "text": legacy["full_text"],
                "raw_data": data,
            }
        )
        return cls(**values)
