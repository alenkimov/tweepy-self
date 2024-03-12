from datetime import datetime, timedelta

from pydantic import BaseModel

from .utils import to_datetime


class Image(BaseModel):
    type: str
    width: int
    height: int


class Media(BaseModel):
    image: Image
    size: int
    id: int
    expires_at: datetime

    @classmethod
    def from_raw_data(cls, data: dict):
        # image_data = {
        #     "type": data["image"]["image_type"],
        #     "width": data["image"]["w"],
        #     "height": data["image"]["h"],
        # }
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
