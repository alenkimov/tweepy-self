# Tweepy-self
[![Telegram channel](https://img.shields.io/endpoint?url=https://runkit.io/damiankrawczyk/telegram-badge/branches/master?url=https://t.me/cum_insider)](https://t.me/cum_insider)
[![PyPI version info](https://img.shields.io/pypi/v/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)
[![PyPI supported Python versions](https://img.shields.io/pypi/pyversions/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)
[![PyPI downloads per month](https://img.shields.io/pypi/dm/tweepy-self.svg)](https://pypi.python.org/pypi/tweepy-self)

A modern, easy to use, feature-rich, and async ready API wrapper for Twitter's user API written in Python.

_NEW!_ Менеджер аккаунтов с базой данных:
- [tweepy-manager](https://github.com/alenkimov/tweepy-manager)

More libraries of the family:
- [better-proxy](https://github.com/alenkimov/better_proxy)
- [better-web3](https://github.com/alenkimov/better_web3)

Отдельное спасибо [Кузнице Ботов](https://t.me/bots_forge) за код для авторизации и разморозки! Подписывайтесь на их Telegram :)

Похожие библиотеки:
- [twikit (sync and async)](https://github.com/d60/twikit)
- [twitter-api-client (sync)](https://github.com/trevorhobenshield/twitter-api-client)

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

twitter_account = twitter.Account(auth_token="auth_token")

async def main():
    async with twitter.Client(twitter_account) as twitter_client:
        print(f"Logged in as @{twitter_account.username} (id={twitter_account.id})")
        tweet = await twitter_client.tweet("Hello tweepy-self! <3")
        print(tweet)

if __name__ == "__main__":
    asyncio.run(main())
```

## Документация
### Некоторые истины
Имена пользователей нужно передавать БЕЗ знака `@`.
Чтобы наверняка убрать этот знак можно передать имя пользователя в функцию `twitter.utils.remove_at_sign()`

Automating user accounts is against the Twitter ToS. This library is a proof of concept and I cannot recommend using it. Do so at your own risk

### Как включить логирование
```python
import sys
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")
logger.enable("twitter")
```

`level="DEBUG"` позволяет увидеть информацию обо всех запросах.

### Аккаунт
`twitter.Account`

#### Статусы аккаунта
- `UNKNOWN` - Статус аккаунта не установлен. Это статус по умолчанию.
- `BAD_TOKEN` - Неверный или мертвый токен.
- `SUSPENDED` - Действие учетной записи приостановлено. Тем не менее возможен запрос данных, а также авторизация через OAuth и OAuth2.
- `LOCKED` - Учетная запись заморожена (лок). Для разморозки (анлок) требуется прохождение капчи (funcaptcha).
- `CONSENT_LOCKED` - Учетная запись заморожена (лок). Условия для разморозки неизвестны.
- `GOOD` - Аккаунт в порядке.

Метод `Client.establish_status()` устанавливает статус аккаунта.
Также статус аккаунта может изменить любое взаимодействие с Twitter.
Поэтому, во время работы может внезапно быть вызвано исключение семейства `twitter.errors.BadAccount`.

Не каждое взаимодействие с Twitter достоверно определяет статус аккаунта.
Например, простой запрос данных об аккаунте честно вернет данные и не изменит статус, даже если действие вашей учетной записи приостановлено (`SUSPENDED`).

### Клиент
`twitter.Client`

#### Настройка
Клиент может быть сконфигурирован перед работой. Он принимает в себя следующие параметры:
- `wait_on_rate_limit` Если включено, то при достижении Rate Limit будет ждать, вместо того, чтобы выбрасывать исключение. Включено по умолчанию.
- `capsolver_api_key` API ключ сервиса [CapSolver](https://dashboard.capsolver.com/passport/register?inviteCode=m-aE3NeBGZLU). Нужен для автоматической разморозки аккаунта.
- `max_unlock_attempts` Максимальное количество попыток разморозки аккаунта. По умолчанию: 5.
- `auto_relogin` Если включено, то при невалидном токене (`BAD_TOKEN`) и предоставленных данных для авторизации (имя пользователя, пароль и totp_secret) будет произведен автоматический релогин (замена токена). Включено по умолчанию.
- `update_account_info_on_startup` Если включено, то на старте будет автоматически запрошена информация об аккаунте, а также установлен его статус. Включено по умолчанию.
- `**session_kwargs` Любые параметры, которые может принимать сессия `curl_cffi.requests.AsyncSession`. Например, можно передать параметр `proxy`.

Пример настройки клиента:
```python
async with twitter.Client(
    twitter_account,
    capsolver_api_key="CAP-00000000000000000000000000000000",
    proxy="http://login:password@ip:port",  # Можно передавать в любом формате, так как используется библиотека better_proxy
) as twitter_client:
    ...
```

### Доступные методы
Список всех методов.

#### Запрос информации о собственном аккаунте
```python
twitter_client.update_account_info()
print(twitter_client.account)
```

#### Запрос пользователя по username или по ID

```python
bro = twitter_client.request_user_by_username(bro_username)
bro = twitter_client.request_user_by_id(bro_id)
bros = twitter_client.request_users_by_ids([bro1_id, bro2_id, ...])
```

####  Загрузка изображения на сервер, смена аватарки и баннера
```python
image = open("image.png", "rb").read()
media = await twitter_client.upload_image(image)
avatar_image_url = await twitter_client.update_profile_avatar(media.id)
banner_image_url = await twitter_client.update_profile_banner(media.id)
```

#### Изменения данных профиля
```python
await twitter_client.update_birthdate(day=1, month=12, year=2000)
await twitter_client.update_profile(  # Locks account!
    name="New Name",
    description="New description",
    location="New York",
    website="https://github.com/alenkimov/tweepy-self",
)
```

#### Включение TOTP (2FA)
```python
if await twitter_client.totp_is_enabled():
    print(f"TOTP уже включен.")
    return

await twitter_client.enable_totp()
```

#### Логин, если включен TOTP (2FA)
```python
import twitter

twitter_account = twitter.Account(auth_token="...", username="...", password="...", totp_secret="...")
await twitter_client.login()
print(f"Logged in! New auth_token: {twitter_account.auth_token}")
```

#### Смена имени пользователя и пароля
```python
twitter_account = twitter.Account("auth_token", password="password")
...
await twitter_client.change_username("new_username")
await twitter_client.request_user()
print(f"New username: {twitter_account.username}")

await twitter_client.change_password("new_password")
print(f"New password: {twitter_account.password}")
print(f"New auth_token: {twitter_account.auth_token}")
```

#### Авторизация с OAuth
```python
auth_code = await twitter_client.oauth(oauth_token, **oauth_params)
```

#### Авторизация с OAuth2
```python
# Изучите запросы сервиса и найдите подобные данные для авторизации (привязки):
oauth2_data = {
    'response_type': 'code',
    'client_id': 'TjFVQm52ZDFGWEtNT0tKaktaSWU6MTpjaQ',
    'redirect_uri': 'https://waitlist.lens.xyz/tw/',
    'scope': 'users.read tweet.read offline.access',
    'state': 'state',  # Может быть как статичным, так и динамическим.
    'code_challenge': 'challenge',
    'code_challenge_method': 'plain'
}

auth_code = await twitter_client.oauth2(**oauth2_data)
# Передайте код авторизации (привязки) сервису.
# Сервис также может потребовать state, если он динамический.
```

#### Отправка сообщения:
```python
bro = await twitter_client.request_user("bro_username")
await twitter_client.send_message(bro.id, "I love you!")
```

#### Запрос входящих сообщений:
```python
messages = await twitter_client.request_messages()
for message in messages:
    message_data = message["message_data"]
    recipient_id = message_data["recipient_id"]
    sender_id = message_data["sender_id"]
    text = message_data["text"]
    print(f"[id  {sender_id}] -> [id {recipient_id}]: {text}")
```

Так как мне почти не приходилось работать с сообщениями, я еще не сделал для этого удобных моделей.
Поэтому приходится работать со словарем.

#### Пост (твит)
```python
tweet = await twitter_client.tweet("I love you tweepy-self! <3")
print(f"Любовь выражена! Tweet id: {tweet.id}")
```

#### Лайк, репост (ретвит), коммент (реплай)
```python
# Лайк
print(f"Tweet {tweet_id} is liked: {await twitter_client.like(tweet_id)}")

# Репост (ретвит)
print(f"Tweet {tweet_id} is retweeted. Tweet id: {await twitter_client.repost(tweet_id)}")

# Коммент (реплай)
print(f"Tweet {tweet_id} is replied. Reply id: {await twitter_client.reply(tweet_id, 'tem razão')}")
```

#### Цитата
```python
tweet_url = 'https://twitter.com/CreamIce_Cone/status/1691735090529976489'
# Цитата (Quote tweet)
quote_tweet_id = await twitter_client.quote(tweet_url, 'oh....')
print(f"Quoted! Tweet id: {quote_tweet_id}")
```

#### Подписка и отписка
```python
# Подписываемся на Илона Маска
print(f"@{elonmusk.username} is followed: {await twitter_client.follow(elonmusk.id)}")

# Отписываемся от Илона Маска
print(f"@{elonmusk.username} is unfollowed: {await twitter_client.unfollow(elonmusk.id)}")
```

#### Закрепление твита
```python
pinned = await twitter_client.pin_tweet(tweet_id)
print(f"Tweet is pined: {pinned}")
```

#### Запрос своих и чужих подписчиков
```python

followers = await twitter_client.request_followers()
print("Твои подписчики:")
for user in followers:
    print(user)
    
followings = await twitter_client.request_followings()
print(f"Ты подписан на:")
for user in followings:
    print(user)

bro_followers = await twitter_client.request_followers(bro_id)
print(f"Подписчики твоего бро (id={bro_id}):")
for user in bro_followers:
    print(user)

bro_followings = await twitter_client.request_followings(bro_id)
print(f"На твоего бро (id={bro_id}) подписаны:")
for user in bro_followings:
    print(user)
```

#### Голосование
```python
vote_data = await twitter_client.vote(tweet_id, card_id, choice_number)
votes_count = vote_data["card"]["binding_values"]["choice1_count"]["string_value"]
print(f"Votes: {votes_count}")
```

Так как мне почти не приходилось работать с голосованиями, я еще не сделал для этого удобных моделей.
Поэтому приходится работать со словарем.
