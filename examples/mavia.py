from itertools import cycle
import asyncio
from pathlib import Path

from better_proxy import Proxy
import twitter

TWITTERS_TXT = Path("twitters.txt")
PROXIES_TXT = Path("proxies.txt")
RESULTS_TXT = Path("results.txt")
MESSAGES_TXT = Path("quote_messages.txt")

for filepath in (TWITTERS_TXT, PROXIES_TXT, RESULTS_TXT, MESSAGES_TXT):
    filepath.touch(exist_ok=True)

AVATARS_DIR = Path("avatars")
BANNERS_DIR = Path("banners")
SCREENSHOTS_DIR = Path("screenshots")

for dirpath in (AVATARS_DIR, BANNERS_DIR, SCREENSHOTS_DIR):
    dirpath.mkdir(exist_ok=True)

TWITTER_ACCOUNTS = twitter.account.load_accounts_from_file(TWITTERS_TXT)
PROXIES = Proxy.from_file(PROXIES_TXT)

if not PROXIES:
    PROXIES = [None]

QUOT_MESSAGE_URL = "https://twitter.com/Bybit_Official/status/1754416124207181938"
USER_IDS_TO_FOLLOW = [
    999947328621395968,  # https://twitter.com/Bybit_Official
    1451208655752282116,  # https://twitter.com/MaviaGame
]


async def main():
    proxy_to_account_list = list(zip(cycle(PROXIES), TWITTER_ACCOUNTS))

    for (
        (proxy, twitter_account),
        quote_message_text,
        screenshot_path,
        avatar_path,
        banner_path,
    ) in zip(
        proxy_to_account_list,
        open(MESSAGES_TXT, "r").readlines(),
        SCREENSHOTS_DIR.iterdir(),
        AVATARS_DIR.iterdir(),
        BANNERS_DIR.iterdir(),
    ):  # type: (Proxy, twitter.Account), str, Path, Path, Path
        async with twitter.Client(twitter_account, proxy=proxy) as twitter_client:
            await twitter_client.request_user_data()

            # Подписка
            for user_id in USER_IDS_TO_FOLLOW:
                await twitter_client.follow(user_id)
                print(f"{twitter_account} Подписался на {user_id}")
                await asyncio.sleep(10)

            # Твит
            image = open(screenshot_path, "rb").read()
            media_id = await twitter_client.upload_image(image)
            tweet_id = await twitter_client.quote(
                QUOT_MESSAGE_URL, quote_message_text, media_id=media_id
            )
            tweet_url = twitter.utils.tweet_url(twitter_account.username, tweet_id)
            print(f"{twitter_account} Сделал Quote твит: {tweet_url}")
            print(f"\tТекст: {quote_message_text}")
            with open(RESULTS_TXT, "a") as results_file:
                results_file.write(tweet_url)
            await asyncio.sleep(10)

            # Установка аватарки
            image = open(avatar_path, "rb").read()
            media_id = await twitter_client.upload_image(image)
            image_url = await twitter_client.update_profile_avatar(media_id)
            print(f"{twitter_account} Установил эту аватарку: {image_url}")
            await asyncio.sleep(10)

            # Установка баннера
            image = open(banner_path, "rb").read()
            media_id = await twitter_client.upload_image(image)
            image_url = await twitter_client.update_profile_banner(media_id)
            print(f"{twitter_account} Установил этот банер: {image_url}")


if __name__ == "__main__":
    asyncio.run(main())
