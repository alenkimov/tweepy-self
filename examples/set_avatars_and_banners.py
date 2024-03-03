from itertools import cycle
import asyncio
from pathlib import Path
from typing import Optional

from better_proxy import Proxy
import twitter

TWITTERS_TXT = Path("twitters.txt")
PROXIES_TXT = Path("proxies.txt")

for filepath in (TWITTERS_TXT, PROXIES_TXT):
    filepath.touch(exist_ok=True)

AVATARS_DIR = Path("avatars")
BANNERS_DIR = Path("banners")

for dirpath in (AVATARS_DIR, BANNERS_DIR):
    dirpath.mkdir(exist_ok=True)

TWITTER_ACCOUNTS = twitter.account.load_accounts_from_file(TWITTERS_TXT)
PROXIES = Proxy.from_file(PROXIES_TXT)

if not PROXIES:
    PROXIES = [None]

semaphore = asyncio.Semaphore(10)  # Ограничение на 10 одновременных задач


async def handle_account(
    proxy: Optional[Proxy],
    twitter_account: twitter.Account,
    avatar_path: Path,
    banner_path: Path,
):
    async with semaphore, twitter.Client(
        twitter_account, proxy=proxy
    ) as twitter_client:
        try:
            await twitter_client.establish_status()

            if twitter_account.status != "GOOD":
                print(f"{twitter_account} {twitter_account.status}")
                return

            await twitter_client.request_user_data()

            try:
                # Установка аватарки
                with open(avatar_path, "rb") as avatar_file:
                    image = avatar_file.read()
                media_id = await twitter_client.upload_image(
                    image, timeout=120, attempts=5
                )
                image_url = await twitter_client.update_profile_avatar(media_id)
                print(f"{twitter_account} Установил эту аватарку: {image_url}")
                await asyncio.sleep(1)
            except Exception as exc:
                print(f"Не удалось установить аватарку: {exc}")

            try:
                # Установка баннера
                with open(banner_path, "rb") as banner_file:
                    image = banner_file.read()
                media_id = await twitter_client.upload_image(
                    image, timeout=120, attempts=5
                )
                image_url = await twitter_client.update_profile_banner(media_id)
                print(f"{twitter_account} Установил этот банер: {image_url}")
                await asyncio.sleep(1)
            except Exception as exc:
                print(f"Не удалось установить баннер: {exc}")
        except Exception as exc:
            print(f"Пиздец какой-то: {exc}")


async def main():
    tasks = []
    proxy_to_account_list = list(zip(cycle(PROXIES), TWITTER_ACCOUNTS))
    avatar_paths = list(AVATARS_DIR.iterdir())
    banner_paths = list(BANNERS_DIR.iterdir())

    for i, ((proxy, twitter_account), avatar_path, banner_path) in enumerate(
        zip(proxy_to_account_list, cycle(avatar_paths), cycle(banner_paths))
    ):
        task = handle_account(proxy, twitter_account, avatar_path, banner_path)
        tasks.append(task)

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
