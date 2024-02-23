from itertools import cycle
import asyncio
from pathlib import Path

import curl_cffi
from better_proxy import Proxy
import twitter

TWITTERS_TXT = Path("twitters.txt")
PROXIES_TXT = Path("proxies.txt")
RESULTS_TXT = Path("results.txt")
DYM_MESSAGES_TXT = Path("dym_messages.txt")
MAVIA_MESSAGES_TXT = Path("mavia_messages.txt")

for filepath in (
    TWITTERS_TXT,
    PROXIES_TXT,
    RESULTS_TXT,
    DYM_MESSAGES_TXT,
    MAVIA_MESSAGES_TXT,
):
    filepath.touch(exist_ok=True)

SCREENSHOTS_DIR = Path("screenshots")

for dirpath in (SCREENSHOTS_DIR,):
    dirpath.mkdir(exist_ok=True)

TWITTER_ACCOUNTS = twitter.account.load_accounts_from_file(TWITTERS_TXT)
PROXIES = Proxy.from_file(PROXIES_TXT)

if not PROXIES:
    PROXIES = [None]

QUOT_MAVIA_TWEET_URL = "https://twitter.com/Bybit_Official/status/1754416124207181938"
QUOT_DYM_TWEET_URL = "https://twitter.com/Bybit_Official/status/1760246614252286288"
USER_IDS_TO_FOLLOW = [
    999947328621395968,  # https://twitter.com/Bybit_Official
    1451208655752282116,  # https://twitter.com/MaviaGame
    1506297383793176584,  # https://twitter.com/dymension
]


async def main():
    proxy_to_account_list = list(zip(cycle(PROXIES), TWITTER_ACCOUNTS))

    for (
        (proxy, twitter_account),
        dym_quote_message_text,
        mavia_quote_message_text,
        screenshot_path,
    ) in zip(
        proxy_to_account_list,
        open(DYM_MESSAGES_TXT, "r").readlines(),
        open(MAVIA_MESSAGES_TXT, "r").readlines(),
        SCREENSHOTS_DIR.iterdir(),
    ):  # type: (Proxy, twitter.Account), str, str, Path,
        async with twitter.Client(twitter_account, proxy=proxy) as twitter_client:
            try:
                await twitter_client.request_user_data()

                # Подписка
                for user_id in USER_IDS_TO_FOLLOW:
                    await twitter_client.follow(user_id)
                    print(f"{twitter_account} Подписался на {user_id}")
                    await asyncio.sleep(3)

                # Твит DYM
                dym_tweet = await twitter_client.quote(
                    QUOT_DYM_TWEET_URL, dym_quote_message_text
                )
                print(f"{twitter_account} Сделал Quote твит (DYM): {dym_tweet.url}")
                print(f"\tТекст: {dym_tweet.full_text}")
                await asyncio.sleep(3)

                # Твит Mavia
                image = open(screenshot_path, "rb").read()
                media_id = await twitter_client.upload_image(image)
                mavia_tweet = await twitter_client.quote(
                    QUOT_MAVIA_TWEET_URL,
                    mavia_quote_message_text,
                    media_id=media_id,
                )
                print(f"{twitter_account} Сделал Quote твит (MAVIA): {mavia_tweet.url}")
                print(f"\tТекст: {mavia_tweet.full_text}")
                print(f"\tСкриншот: {screenshot_path.stem}")
                await asyncio.sleep(3)

                with open(RESULTS_TXT, "a") as results_file:
                    results_file.write(
                        f"{twitter_account.auth_token},{screenshot_path.stem},{mavia_tweet.url},{dym_tweet.url}\n"
                    )

            except curl_cffi.requests.errors.RequestsError as exc:
                print(f"Ошибка запроса. Возможно, плохой прокси: {exc}")
                continue
            except Exception as exc:
                print(f"Что-то очень плохое: {exc}")
                continue


if __name__ == "__main__":
    asyncio.run(main())
