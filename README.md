# Tweepy-self
[![Telegram channel](https://img.shields.io/endpoint?url=https://runkit.io/damiankrawczyk/telegram-badge/branches/master?url=https://t.me/cum_insider)](https://t.me/cum_insider)
[![PyPI version info](https://img.shields.io/pypi/v/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)
[![PyPI supported Python versions](https://img.shields.io/pypi/pyversions/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)

A modern, easy to use, feature-rich, and async ready API wrapper for Twitter's user API written in Python.

- Docs (soon)

More libraries of the family:
- [better-web3](https://github.com/alenkimov/better_web3)
- [better-proxy](https://github.com/alenkimov/better_proxy)

Отдельное спасибо [Кузнице Ботов](https://t.me/bots_forge), как соавторам! Подписывайтесь на их Telegram :)

## Key Features
- Modern Pythonic API using async and await.
- Prevents user account automation detection.

## Installing
```bash
pip install tweepy-self
```

## Example
```python
import asyncio
import twitter

account = twitter.Account("auth_token")

async def main():
    async with twitter.Client(account) as twitter_client:
        await twitter_client.tweet("Hello, tweepy-self! <3")

asyncio.run(main())
```

## More
Automating user accounts is against the Twitter ToS. This library is a proof of concept and I cannot recommend using it. Do so at your own risk
