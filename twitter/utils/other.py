from datetime import datetime


def remove_at_sign(username: str) -> str:
    if username.startswith("@"):
        return username[1:]
    return username


def tweet_url(username: str, tweet_id: int) -> str:
    """
    :return: Tweet URL
    """
    return f"https://x.com/{username}/status/{tweet_id}"


def tweets_data_from_instructions(instructions: dict) -> list[dict]:
    tweets = []
    for instruction in instructions:
        if instruction["type"] == "TimelineAddEntries":
            for entry in instruction["entries"]:
                if entry["entryId"].startswith("tweet-"):
                    tweet_data = entry["content"]["itemContent"]["tweet_results"][
                        "result"
                    ]
                    tweets.append(tweet_data)
    return tweets


def to_datetime(twitter_datetime: str):
    return datetime.strptime(twitter_datetime, "%a %b %d %H:%M:%S +0000 %Y")


def hidden_value(value: str) -> str:
    start = value[:3]
    end = value[-3:]
    return f"{start}**{end}"
