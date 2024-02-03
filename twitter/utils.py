from datetime import datetime

from bs4 import BeautifulSoup


def parse_oauth_html(html: str) -> tuple[str | None, str | None, str | None]:
    """
    :return: authenticity_token, redirect_url, redirect_after_login_url
    """
    soup = BeautifulSoup(html, "lxml")
    authenticity_token_element = soup.find("input", {"name": "authenticity_token"})
    authenticity_token = authenticity_token_element.get("value") if authenticity_token_element else None
    redirect_url_element = soup.find("a", text="click here to continue")
    redirect_url = redirect_url_element.get("href") if redirect_url_element else None
    redirect_after_login_element = soup.find("input", {"name": "redirect_after_login"})
    redirect_after_login_url = redirect_after_login_element.get("value") if redirect_after_login_element else None
    return authenticity_token, redirect_url, redirect_after_login_url


def parse_unlock_html(html: str) -> tuple[str | None, str | None, bool]:
    """
    :return: authenticity_token, assignment_token, needs_unlock
    """
    soup = BeautifulSoup(html, "lxml")
    authenticity_token_element = soup.find("input", {"name": "authenticity_token"})
    authenticity_token = authenticity_token_element.get("value") if authenticity_token_element else None
    assignment_token_element = soup.find("input", {"name": "assignment_token"})
    assignment_token = assignment_token_element.get("value") if assignment_token_element else None
    verification_string = soup.find('input', id='verification_string')
    needs_unlock = bool(verification_string)
    return authenticity_token, assignment_token, needs_unlock


def remove_at_sign(username: str) -> str:
    if username.startswith("@"):
        return username[1:]
    return username


def tweet_url(username: str, tweet_id: int) -> str:
    """
    :return: Tweet URL
    """
    return f"https://x.com/{username}/status/{tweet_id}"


def to_datetime(twitter_datetime: str):
    return datetime.strptime(twitter_datetime, '%a %b %d %H:%M:%S +0000 %Y')


def hidden_value(value: str) -> str:
    start = value[:3]
    end = value[-3:]
    return f"{start}**{end}"
