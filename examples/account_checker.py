"""
Скрипт для установки статуса Twitter аккаунтов (проверка на бан).
"""

import asyncio
from itertools import cycle
from pathlib import Path
from typing import Iterable

from curl_cffi import requests
from better_proxy import Proxy
from twitter.utils import load_lines, write_lines
import twitter


TwitterAccountWithAdditionalData = tuple[str, twitter.Account]
SortedAccounts = dict[twitter.AccountStatus: TwitterAccountWithAdditionalData]

INPUT_OUTPUT_DIR = Path("input-output")
INPUT_OUTPUT_DIR.mkdir(exist_ok=True)

PROXIES_TXT = INPUT_OUTPUT_DIR / "PROXIES.txt"
ACCOUNTS_TXT = INPUT_OUTPUT_DIR / f"{twitter.AccountStatus.UNKNOWN}.txt"
[filepath.touch() for filepath in (PROXIES_TXT, ACCOUNTS_TXT)]

SEPARATOR = ":"


def sort_accounts(
        accounts: Iterable[TwitterAccountWithAdditionalData]
) -> SortedAccounts:
    status_to_account_with_additional_data = {status: list() for status in twitter.AccountStatus}
    for additional_data, account in accounts:
        status_to_account_with_additional_data[account.status].append((additional_data, account))
    return status_to_account_with_additional_data


def save_sorted_accounts_with_additional_data(sorted_accounts: dict[twitter.AccountStatus: (str, twitter.Account)]):
    for status, accounts_with_additional_data in sorted_accounts.items():
        filepath = INPUT_OUTPUT_DIR / f'{status}.txt'
        lines = [additional_data for additional_data, account in accounts_with_additional_data]
        write_lines(filepath, lines)


def load_accounts_with_additional_data() -> list[TwitterAccountWithAdditionalData]:
    accounts = list()
    for file in INPUT_OUTPUT_DIR.iterdir():
        if file.is_file() and file.stem in twitter.AccountStatus.__members__:
            status = file.stem
            for additional_data in load_lines(file):
                auth_token = additional_data.split(SEPARATOR)[0]
                account = twitter.Account(auth_token=auth_token)
                account.status = status
                accounts.append((additional_data, account))
    return accounts


def print_statistic(sorted_accounts: SortedAccounts):
    for status, accounts_with_additional_data in sorted_accounts.items():
        print(f"{status}: {len(accounts_with_additional_data)}")


async def establish_account_status(account: twitter.Account, proxy: Proxy = None):
    async with twitter.Client(account, proxy=proxy) as twitter_client:
        try:
            await twitter_client.establish_status()
        except requests.errors.RequestsError:
            pass

    print(f"{proxy.fixed_length} {account} {account.status}")


async def check_accounts(
        accounts: Iterable[TwitterAccountWithAdditionalData],
        proxies: Iterable[Proxy],
):
    sorted_accounts = sort_accounts(accounts)
    print_statistic(sorted_accounts)

    if not proxies:
        proxies = [None]

    proxy_to_account_list = list(zip(cycle(proxies), accounts))

    tasks = []
    for proxy, account_with_additional_data in proxy_to_account_list:
        account = account_with_additional_data[1]
        if account.status == twitter.AccountStatus.UNKNOWN:
            tasks.append(establish_account_status(account, proxy=proxy))
    try:
        await asyncio.gather(*tasks)
    finally:
        sorted_accounts = sort_accounts(accounts)
        save_sorted_accounts_with_additional_data(sorted_accounts)
        print_statistic(sorted_accounts)


if __name__ == '__main__':
    proxies = Proxy.from_file(PROXIES_TXT)
    print(f"Прокси: {len(proxies)}")
    if not proxies:
        print(f"(Необязательно) Внесите прокси в любом формате"
              f"\n\tв файл по пути {PROXIES_TXT}")

    accounts = load_accounts_with_additional_data()
    if not accounts:
        print(f"Внесите аккаунты в формате auth_token:data1:data2:..."
              f" (auth_token - обязательный параметр, остальное - любая другая информация об аккаунте)"
              f"\n\tв файл по пути {ACCOUNTS_TXT}")
        quit()

    asyncio.run(check_accounts(accounts, proxies))
