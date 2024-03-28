"""
pip install tweepy-self
python xai.py
"""

from itertools import cycle
import asyncio
from pathlib import Path

import curl_cffi
from better_proxy import Proxy
import twitter

TWITTERS_TXT = Path("twitters.txt")
PROXIES_TXT = Path("proxies.txt")
RESULTS_TXT = Path("results.txt")
XAI_MESSAGES_TXT = Path("xai_messages.txt")

for filepath in (
    TWITTERS_TXT,
    PROXIES_TXT,
    RESULTS_TXT,
    XAI_MESSAGES_TXT,
):
    filepath.touch(exist_ok=True)


TWITTER_ACCOUNTS = twitter.account.load_accounts_from_file(TWITTERS_TXT)
PROXIES = Proxy.from_file(PROXIES_TXT)

if not PROXIES:
    PROXIES = [None]

QUOT_TWEET_URL = "https://twitter.com/Bybit_Official/status/1767120261961097328"
USER_IDS_TO_FOLLOW = [
    999947328621395968,  # https://twitter.com/Bybit_Official
    1351271303823585282,  # https://twitter.com/xai_games
    1659498055895502849,  # https://twitter.com/TarochiGame
]

CAPSOLVER_API_KEY = None  # To auto-unlock


async def main():
    proxy_to_account_list = list(zip(cycle(PROXIES), TWITTER_ACCOUNTS))

    for (proxy, twitter_account), xai_quote_message_text in zip(
        proxy_to_account_list,
        open(XAI_MESSAGES_TXT, "r").readlines(),
    ):  # type: (Proxy, twitter.Account), str,
        async with twitter.Client(
            twitter_account,
            proxy=proxy,
            capsolver_api_key=CAPSOLVER_API_KEY,
        ) as twitter_client:
            try:
                # Подписка
                for user_id in USER_IDS_TO_FOLLOW:
                    await twitter_client.follow(user_id)
                    print(f"{twitter_account} Подписался на {user_id}")
                    await asyncio.sleep(3)

                # Твит
                xai_tweet = await twitter_client.quote(
                    QUOT_TWEET_URL, xai_quote_message_text
                )
                print(f"{twitter_account} Сделал Quote твит (XAI): {xai_tweet.url}")
                print(f"\tТекст: {xai_tweet.text}")
                await asyncio.sleep(3)

                with open(RESULTS_TXT, "a") as results_file:
                    results_file.write(
                        f"{twitter_account.auth_token},@{twitter_account.username},{xai_tweet.url}\n"
                    )

            except curl_cffi.requests.errors.RequestsError as exc:
                print(f"Ошибка запроса. Возможно, плохой прокси: {exc}")
                with open(RESULTS_TXT, "a") as results_file:
                    results_file.write(
                        f"{twitter_account.auth_token},@{twitter_account.username},ERROR\n"
                    )
                continue
            except Exception as exc:
                print(f"Что-то очень плохое: {exc}")
                with open(RESULTS_TXT, "a") as results_file:
                    results_file.write(
                        f"{twitter_account.auth_token},@{twitter_account.username},ERROR\n"
                    )
                continue


if __name__ == "__main__":
    asyncio.run(main())
