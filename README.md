# Tweepy-self
[![Telegram channel](https://img.shields.io/endpoint?url=https://runkit.io/damiankrawczyk/telegram-badge/branches/master?url=https://t.me/cum_insider)](https://t.me/cum_insider)
[![PyPI version info](https://img.shields.io/pypi/v/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)
[![PyPI supported Python versions](https://img.shields.io/pypi/pyversions/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)

A modern, easy to use, feature-rich, and async ready API wrapper for Twitter's user API written in Python.

- Docs (soon)

More libraries of the family:
- [better-web3](https://github.com/alenkimov/better_web3)
- [better-proxy](https://github.com/alenkimov/better_proxy)
- [better-automation](https://github.com/alenkimov/better_automation)

Отдельное спасибо [Кузнице Ботов](https://t.me/bots_forge) за код для авторизации и разморозки! Подписывайтесь на их Telegram :)

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

account = twitter.Account(auth_token="auth_token")

async def main():
    async with twitter.Client(account) as twitter_client:
        await twitter_client.tweet("Hello, tweepy-self! <3")

asyncio.run(main())
```

## More
Automating user accounts is against the Twitter ToS. This library is a proof of concept and I cannot recommend using it. Do so at your own risk

## Документация (устаревшая)
`Код ушел немного дальше, чем эта документация.`

Библиотека позволяет работать с неофициальным API Twitter, а именно:
- Логин
- Анлок
- Привязывать сервисы (приложения).
- Устанавливать статус аккаунта (бан, лок).
- Загружать изображения на сервер и изменять баннер и аватарку.
- Изменять данные о пользователе: имя, описание профиля и другое.
- Изменять имя пользователя и пароль.
- Запрашивать информацию о подписчиках.
- Запрашивать некоторую информацию о пользователе (количество подписчиков и другое).
- Голосовать.
- Подписываться и отписываться.
- Лайкать и дизлайкать.
- Твиттить, ретвиттить с изображением и без.
- Закреплять твиты.
- Запрашивать твиты пользователей.
- Удалять твиты.
- И другое.

#### Статус аккаунта
После любого взаимодействия с Twitter устанавливается статус аккаунта:
- `BAD_TOKEN` - Неверный токен.
- `UNKNOWN` - Статус аккаунта не установлен.
- `SUSPENDED` - Действие учетной записи приостановлено (бан).
- `LOCKED` - Учетная запись заморожена (лок) (требуется прохождение капчи).
- `GOOD` - Аккаунт в порядке.

Не каждое взаимодействие с Twitter достоверно определяет статус аккаунта.
Например, простой запрос данных об аккаунте честно вернет данные, даже если ваш аккаунт заморожен.

Для достоверной установки статуса аккаунта используйте метод `establish_status()`

### Примеры работы
Запрос информации о пользователе:
```python
# Запрос информации о текущем пользователе:
me = await twitter_client.request_user_data()
print(f"[{account.short_auth_token}] {me}")
print(f"Аккаунт создан: {me.created_at}")
print(f"Following (подписан ты): {me.followings_count}")
print(f"Followers (подписаны на тебя): {me.followers_count}")
print(f"Прочая информация: {me.raw_data}")

# Запрос информации об ином пользователе:
elonmusk = await twitter.request_user_data("@elonmusk")
print(elonmusk)
```

Смена имени пользователя и пароля:
```python
account = twitter.Account("auth_token", password="password")
...
await twitter_client.change_username("new_username")
await twitter_client.request_user_data()
print(f"New username: {account.data.username}")

await twitter_client.change_password("new_password")
print(f"New password: {account.password}")
print(f"New auth_token: {account.auth_token}")
```

Смена данных профиля:
```python
await twitter_client.update_birthdate(day=1, month=12, year=2000)
await twitter_client.update_profile(  # Locks account!
    name="New Name",
    description="New description",
    location="New York",
    website="https://github.com/alenkimov/better_automation",
)
```

Загрузка изображений и смена аватара и баннера:
```python
image = open(f"image.png", "rb").read()
media_id = await twitter_client.upload_image(image)
avatar_image_url = await twitter_client.update_profile_avatar(media_id)
banner_image_url = await twitter_client.update_profile_banner(media_id)
```

Привязка сервиса (приложения):

```python
# Изучите запросы сервиса и найдите подобные данные для авторизации (привязки):
bind_data = {
    'response_type': 'code',
    'client_id': 'TjFVQm52ZDFGWEtNT0tKaktaSWU6MTpjaQ',
    'redirect_uri': 'https://waitlist.lens.xyz/tw/',
    'scope': 'users.read tweet.read offline.access',
    'state': 'state',  # Может быть как статичным, так и динамическим.
    'code_challenge': 'challenge',
    'code_challenge_method': 'plain'
}

bind_code = await twitter_client.oauth_2(**bind_data)
# Передайте код авторизации (привязки) сервису.
# Сервис также может потребовать state, если он динамический.
```

Отправка сообщения:
```python
bro = await twitter_client.request_user_data("@username")
await twitter_client.send_message(bro.id, "I love you!")
```

Запрос входящих сообщений:
```python
messages = await twitter_client.request_messages()
for message in messages:
    message_data = message["message_data"]
    recipient_id = message_data["recipient_id"]
    sender_id = message_data["sender_id"]
    text = message_data["text"]
    print(f"[id  {sender_id}] -> [id {recipient_id}]: {text}")
```

Другие методы:
```python
# Выражение любви через твит
tweet_id = await twitter_client.tweet("I love YOU! !!!!1!1")
print(f"Любовь выражена! Tweet id: {tweet_id}")

print(f"Tweet is pined: {await twitter_client.pin_tweet(tweet_id)}")

# Лайк
print(f"Tweet {tweet_id} is liked: {await twitter_client.like(tweet_id)}")

# Репост (ретвит)
print(f"Tweet {tweet_id} is retweeted. Tweet id: {await twitter_client.repost(tweet_id)}")

# Коммент (реплай)
print(f"Tweet {tweet_id} is replied. Reply id: {await twitter_client.reply(tweet_id, 'tem razão')}")

# Подписываемся на Илона Маска
print(f"@{elonmusk.username} is followed: {await twitter_client.follow(elonmusk.id)}")

# Отписываемся от Илона Маска
print(f"@{elonmusk.username} is unfollowed: {await twitter_client.unfollow(elonmusk.id)}")

tweet_url = 'https://twitter.com/CreamIce_Cone/status/1691735090529976489'
# Цитата (Quote tweet)
quote_tweet_id = await twitter_client.quote(tweet_url, 'oh....')
print(f"Quoted! Tweet id: {quote_tweet_id}")

# Запрашиваем первых трех подписчиков
# (Параметр count по каким-то причинам работает некорректно)
followers = await twitter_client.request_followers(count=20)
print("Твои подписчики:")
for follower in followers:
    print(follower)
```