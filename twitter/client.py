from typing import Any, Literal, Iterable
from time import time
import asyncio
import base64
import re

from loguru import logger
from curl_cffi import requests
from yarl import URL

from ._capsolver.fun_captcha import FunCaptcha, FunCaptchaTypeEnm

from .errors import (
    TwitterException,
    FailedToFindDuplicatePost,
    HTTPException,
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    RateLimited,
    ServerError,
    BadAccount,
    BadToken,
    Locked,
    ConsentLocked,
    Suspended,
)
from .utils import to_json
from .base import BaseHTTPClient
from .account import Account, AccountStatus
from .models import User, Tweet, Media
from .utils import (
    remove_at_sign,
    parse_oauth_html,
    parse_unlock_html,
    tweets_data_from_instructions,
)


class Client(BaseHTTPClient):
    _BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    _DEFAULT_HEADERS = {
        "authority": "twitter.com",
        "origin": "https://twitter.com",
        "x-twitter-active-user": "yes",
        # 'x-twitter-auth-type': 'OAuth2Session',
        "x-twitter-client-language": "en",
    }
    _GRAPHQL_URL = "https://twitter.com/i/api/graphql"
    _ACTION_TO_QUERY_ID = {
        "CreateRetweet": "ojPdsZsimiJrUGLR1sjUtA",
        "FavoriteTweet": "lI07N6Otwv1PhnEgXILM7A",
        "UnfavoriteTweet": "ZYKSe-w7KEslx3JhSIk5LA",
        "CreateTweet": "SoVnbfCycZ7fERGCwpZkYA",
        "TweetResultByRestId": "V3vfsYzNEyD9tsf4xoFRgw",
        "ModerateTweet": "p'jF:GVqCjTcZol0xcBJjw",
        "DeleteTweet": "VaenaVgh5q5ih7kvyVjgtg",
        "UserTweets": "V1ze5q3ijDS1VeLwLY0m7g",
        "TweetDetail": "VWFGPVAGkZMGRKGe3GFFnA",
        "ProfileSpotlightsQuery": "9zwVLJ48lmVUk8u_Gh9DmA",
        "Following": "t-BPOrMIduGUJWO_LxcvNQ",
        "Followers": "3yX7xr2hKjcZYnXt6cU6lQ",
        "UserByScreenName": "G3KGOASz96M-Qu0nwmGXNg",
        "UsersByRestIds": "itEhGywpgX9b3GJCzOtSrA",
        "Viewer": "W62NnYgkgziw9bwyoVht0g",
    }
    _CAPTCHA_URL = "https://twitter.com/account/access"
    _CAPTCHA_SITE_KEY = "0152B4EB-D2DC-460A-89A1-629838B529C9"

    @classmethod
    def _action_to_url(cls, action: str) -> tuple[str, str]:
        """
        :return: URL and Query ID
        """
        query_id = cls._ACTION_TO_QUERY_ID[action]
        url = f"{cls._GRAPHQL_URL}/{query_id}/{action}"
        return url, query_id

    def __init__(
        self,
        account: Account,
        *,
        wait_on_rate_limit: bool = True,
        capsolver_api_key: str = None,
        max_unlock_attempts: int = 5,
        **session_kwargs,
    ):
        super().__init__(**session_kwargs)
        self.account = account
        self.wait_on_rate_limit = wait_on_rate_limit
        self.capsolver_api_key = capsolver_api_key
        self.max_unlock_attempts = max_unlock_attempts

    async def request(
        self,
        method,
        url,
        auth: bool = True,
        bearer: bool = True,
        **kwargs,
    ) -> tuple[requests.Response, Any]:
        cookies = kwargs["cookies"] = kwargs.get("cookies") or {}
        headers = kwargs["headers"] = kwargs.get("headers") or {}

        if bearer:
            headers["authorization"] = f"Bearer {self._BEARER_TOKEN}"

        if auth:
            if not self.account.auth_token:
                raise ValueError("No auth_token. Login before")

            cookies["auth_token"] = self.account.auth_token
            if self.account.ct0:
                cookies["ct0"] = self.account.ct0
                headers["x-csrf-token"] = self.account.ct0

        # fmt: off
        log_message = f"{self.account} Request {method} {url}"
        if kwargs.get('data'): log_message += f"\nRequest data: {kwargs.get('data')}"
        if kwargs.get('json'): log_message += f"\nRequest data: {kwargs.get('json')}"
        logger.debug(log_message)
        # fmt: on

        try:
            response = await self._session.request(method, url, **kwargs)
        except requests.errors.RequestsError as exc:
            if exc.code == 35:
                msg = (
                    "The IP address may have been blocked by Twitter. Blocked countries: Russia. "
                    + str(exc)
                )
                raise requests.errors.RequestsError(msg, 35, exc.response)
            raise

        data = response.text
        # fmt: off
        log_message = (f"{self.account} Response {method} {url}"
                       f"\nStatus code: {response.status_code}"
                       f"\nResponse data: {data}")
        logger.debug(log_message)
        # fmt: on

        if response.headers["content-type"].startswith("application/json"):
            data = response.json()

        if response.status_code == 429:
            if self.wait_on_rate_limit:
                reset_time = int(response.headers["x-rate-limit-reset"])
                sleep_time = reset_time - int(time()) + 1
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                return await self.request(method, url, auth, bearer, **kwargs)
            raise RateLimited(response, data)

        if response.status_code == 400:
            raise BadRequest(response, data)

        if response.status_code == 401:
            exc = Unauthorized(response, data)

            if 32 in exc.api_codes:
                self.account.status = AccountStatus.BAD_TOKEN
                raise BadToken(exc, self.account)

            raise exc

        if response.status_code == 403:
            exc = Forbidden(response, data)

            if 353 in exc.api_codes and "ct0" in response.cookies:
                self.account.ct0 = response.cookies["ct0"]
                return await self.request(method, url, auth, bearer, **kwargs)

            if 64 in exc.api_codes:
                self.account.status = AccountStatus.SUSPENDED
                raise Suspended(exc, self.account)

            if 326 in exc.api_codes:
                for error_data in exc.api_errors:
                    if (
                        error_data.get("code") == 326
                        and error_data.get("bounce_location") == "/i/flow/consent_flow"
                    ):
                        self.account.status = AccountStatus.CONSENT_LOCKED
                        raise ConsentLocked(exc, self.account)

                self.account.status = AccountStatus.LOCKED
                if not self.capsolver_api_key:
                    raise Locked(exc, self.account)

                await self.unlock()
                return await self.request(method, url, auth, bearer, **kwargs)

            raise exc

        if response.status_code == 404:
            raise NotFound(response, data)

        if response.status_code >= 500:
            raise ServerError(response, data)

        if not 200 <= response.status_code < 300:
            raise HTTPException(response, data)

        if isinstance(data, dict) and "errors" in data:
            exc = HTTPException(response, data)

            if 141 in exc.api_codes:
                self.account.status = AccountStatus.SUSPENDED
                raise Suspended(exc, self.account)

            if 326 in exc.api_codes:
                for error_data in exc.api_errors:
                    if (
                        error_data.get("code") == 326
                        and error_data.get("bounce_location") == "/i/flow/consent_flow"
                    ):
                        self.account.status = AccountStatus.CONSENT_LOCKED
                        raise ConsentLocked(exc, self.account)

                self.account.status = AccountStatus.LOCKED
                if not self.capsolver_api_key:
                    raise Locked(exc, self.account)

                await self.unlock()
                return await self.request(method, url, auth, bearer, **kwargs)

            raise exc

        self.account.status = AccountStatus.GOOD
        return response, data

    async def _request_oauth_2_auth_code(
        self,
        client_id: str,
        code_challenge: str,
        state: str,
        redirect_uri: str,
        code_challenge_method: str,
        scope: str,
        response_type: str,
    ) -> str:
        url = "https://twitter.com/i/api/2/oauth2/authorize"
        querystring = {
            "client_id": client_id,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "scope": scope,
            "response_type": response_type,
            "redirect_uri": redirect_uri,
        }
        response, response_json = await self.request("GET", url, params=querystring)
        auth_code = response_json["auth_code"]
        return auth_code

    async def _confirm_oauth_2(self, auth_code: str):
        data = {
            "approval": "true",
            "code": auth_code,
        }
        headers = {"content-type": "application/x-www-form-urlencoded"}
        await self.request(
            "POST",
            "https://twitter.com/i/api/2/oauth2/authorize",
            headers=headers,
            data=data,
        )

    async def oauth_2(
        self,
        client_id: str,
        code_challenge: str,
        state: str,
        redirect_uri: str,
        code_challenge_method: str,
        scope: str,
        response_type: str,
    ):
        """
        Запрашивает код авторизации для OAuth 2.0 авторизации.

        Привязка (бинд, линк) приложения.

        :param client_id: Идентификатор клиента, используемый для OAuth.
        :param code_challenge: Код-вызов, используемый для PKCE (Proof Key for Code Exchange).
        :param state: Уникальная строка состояния для предотвращения CSRF-атак.
        :param redirect_uri: URI перенаправления, на который будет отправлен ответ.
        :param code_challenge_method: Метод, используемый для преобразования code_verifier в code_challenge.
        :param scope: Строка областей доступа, запрашиваемых у пользователя.
        :param response_type: Тип ответа, который ожидается от сервера авторизации.
        :return: Код авторизации (привязки).
        """
        auth_code = await self._request_oauth_2_auth_code(
            client_id,
            code_challenge,
            state,
            redirect_uri,
            code_challenge_method,
            scope,
            response_type,
        )
        await self._confirm_oauth_2(auth_code)
        return auth_code

    async def _oauth(self, oauth_token: str, **oauth_params) -> requests.Response:
        """

        :return: Response: html страница привязки приложения (аутентификации) старого типа.
        """
        url = "https://api.twitter.com/oauth/authenticate"
        oauth_params["oauth_token"] = oauth_token
        response, _ = await self.request("GET", url, params=oauth_params)

        if response.status_code == 403:
            raise ValueError(
                "The request token (oauth_token) for this page is invalid."
                " It may have already been used, or expired because it is too old."
            )

        return response

    async def _confirm_oauth(
        self,
        oauth_token: str,
        authenticity_token: str,
        redirect_after_login_url: str,
    ) -> requests.Response:
        url = "https://api.twitter.com/oauth/authorize"
        params = {
            "redirect_after_login": redirect_after_login_url,
            "authenticity_token": authenticity_token,
            "oauth_token": oauth_token,
        }
        response, _ = await self.request("POST", url, data=params)
        return response

    async def oauth(self, oauth_token: str, **oauth_params) -> tuple[str, str]:
        """
        :return: authenticity_token, redirect_url
        """
        response = await self._oauth(oauth_token, **oauth_params)
        authenticity_token, redirect_url, redirect_after_login_url = parse_oauth_html(
            response.text
        )

        # Первая привязка требует подтверждения
        if redirect_after_login_url:
            response = await self._confirm_oauth(
                oauth_token, authenticity_token, redirect_after_login_url
            )
            authenticity_token, redirect_url, redirect_after_login_url = (
                parse_oauth_html(response.text)
            )

        return authenticity_token, redirect_url

    async def request_and_set_username(self):
        url = "https://twitter.com/i/api/1.1/account/settings.json"
        response, response_json = await self.request("POST", url)
        self.account.username = response_json["screen_name"]

    async def _request_user(self, username: str) -> User:
        url, query_id = self._action_to_url("UserByScreenName")
        username = remove_at_sign(username)
        variables = {
            "screen_name": username,
            "withSafetyModeUserFields": True,
        }
        features = {
            "hidden_profile_likes_enabled": True,
            "hidden_profile_subscriptions_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        field_toggles = {
            "withAuxiliaryUserLabels": False,
        }
        params = {
            "variables": to_json(variables),
            "features": to_json(features),
            "fieldToggles": to_json(field_toggles),
        }
        response, data = await self.request("GET", url, params=params)
        return User.from_raw_data(data["data"]["user"]["result"])

    async def request_user(
        self, *, username: str = None, user_id: int | str = None
    ) -> User | Account:
        if username and user_id:
            raise ValueError("Specify username or user_id, not both.")

        if user_id:
            users = await self.request_users((user_id,))
            user = users[user_id]
        else:
            if not username:
                if not self.account.username:
                    await self.request_and_set_username()
                username = self.account.username

            user = await self._request_user(username)

        if self.account.username == user.username:
            self.account.update(**user.model_dump())
            user = self.account

        return user

    async def upload_image(
        self,
        image: bytes,
        attempts: int = 3,
        timeout: float | tuple[float, float] = 10,
    ) -> Media:
        """
        Upload image as bytes.

        Иногда при первой попытке загрузки изображения возвращает 408,
        после чего повторная попытка загрузки изображения проходит успешно

        :return: Media
        """
        url = "https://upload.twitter.com/1.1/media/upload.json"

        payload = {"media_data": base64.b64encode(image)}

        for attempt in range(attempts):
            try:
                response, data = await self.request(
                    "POST", url, data=payload, timeout=timeout
                )
                return Media.from_raw_data(data)
            except (HTTPException, requests.errors.RequestsError) as exc:
                if (
                    attempt < attempts - 1
                    and (
                        isinstance(exc, requests.errors.RequestsError)
                        and exc.code == 28
                    )
                    or (
                        isinstance(exc, HTTPException)
                        and exc.response.status_code == 408
                    )
                ):
                    continue
                else:
                    raise

    async def _follow_action(self, action: str, user_id: int | str) -> bool:
        url = f"https://twitter.com/i/api/1.1/friendships/{action}.json"
        params = {
            "include_profile_interstitial_type": "1",
            "include_blocking": "1",
            "include_blocked_by": "1",
            "include_followed_by": "1",
            "include_want_retweets": "1",
            "include_mute_edge": "1",
            "include_can_dm": "1",
            "include_can_media_tag": "1",
            "include_ext_has_nft_avatar": "1",
            "include_ext_is_blue_verified": "1",
            "include_ext_verified_type": "1",
            "include_ext_profile_image_shape": "1",
            "skip_status": "1",
            "user_id": user_id,
        }
        headers = {
            "content-type": "application/x-www-form-urlencoded",
        }
        response, response_json = await self.request(
            "POST", url, params=params, headers=headers
        )
        return bool(response_json)

    async def follow(self, user_id: str | int) -> bool:
        return await self._follow_action("create", user_id)

    async def unfollow(self, user_id: str | int) -> bool:
        return await self._follow_action("destroy", user_id)

    async def _interact_with_tweet(self, action: str, tweet_id: int) -> dict:
        url, query_id = self._action_to_url(action)
        json_payload = {
            "variables": {"tweet_id": tweet_id, "dark_request": False},
            "queryId": query_id,
        }
        response, data = await self.request("POST", url, json=json_payload)
        return data

    async def _repost(self, tweet_id: int | str) -> Tweet:
        data = await self._interact_with_tweet("CreateRetweet", tweet_id)
        tweet_id = data["data"]["create_retweet"]["retweet_results"]["result"]["rest_id"]  # type: ignore
        return await self.request_tweet(tweet_id)

    async def _repost_or_search_duplicate(
        self,
        tweet_id: int,
        *,
        search_duplicate: bool = True,
    ) -> Tweet:
        try:
            tweet = await self._repost(tweet_id)
        except HTTPException as exc:
            if (
                search_duplicate
                and 327
                in exc.api_codes  # duplicate retweet (You have already retweeted this Tweet)
            ):
                tweets = await self.request_tweets(self.account.id)
                duplicate_tweet = None
                for tweet_ in tweets:  # type: Tweet
                    if tweet_.retweeted_tweet and tweet_.retweeted_tweet.id == tweet_id:
                        duplicate_tweet = tweet_

                if not duplicate_tweet:
                    raise FailedToFindDuplicatePost(
                        f"Couldn't find a post duplicate in the next 20 posts"
                    )

                tweet = duplicate_tweet

            else:
                raise

        return tweet

    async def repost(
        self,
        tweet_id: int,
        *,
        search_duplicate: bool = True,
    ) -> Tweet:
        """
        Repost (retweet)

        :return: Tweet
        """
        return await self._repost_or_search_duplicate(
            tweet_id, search_duplicate=search_duplicate
        )

    async def like(self, tweet_id: int) -> bool:
        response_json = await self._interact_with_tweet("FavoriteTweet", tweet_id)
        is_liked = response_json["data"]["favorite_tweet"] == "Done"
        return is_liked

    async def unlike(self, tweet_id: int) -> dict:
        response_json = await self._interact_with_tweet("UnfavoriteTweet", tweet_id)
        is_unliked = (
            "data" in response_json
            and response_json["data"]["unfavorite_tweet"] == "Done"
        )
        return is_unliked

    async def delete_tweet(self, tweet_id: int | str) -> bool:
        url, query_id = self._action_to_url("DeleteTweet")
        json_payload = {
            "variables": {
                "tweet_id": tweet_id,
                "dark_request": False,
            },
            "queryId": query_id,
        }
        response, response_json = await self.request("POST", url, json=json_payload)
        is_deleted = "data" in response_json and "delete_tweet" in response_json["data"]
        return is_deleted

    async def pin_tweet(self, tweet_id: str | int) -> bool:
        url = "https://api.twitter.com/1.1/account/pin_tweet.json"
        data = {
            "tweet_mode": "extended",
            "id": str(tweet_id),
        }
        headers = {
            "content-type": "application/x-www-form-urlencoded",
        }
        response, response_json = await self.request(
            "POST", url, headers=headers, data=data
        )
        is_pinned = bool(response_json["pinned_tweets"])
        return is_pinned

    async def _tweet(
        self,
        text: str = None,
        *,
        media_id: int | str = None,
        tweet_id_to_reply: str | int = None,
        attachment_url: str = None,
    ) -> Tweet:
        url, query_id = self._action_to_url("CreateTweet")
        payload = {
            "variables": {
                "tweet_text": text if text is not None else "",
                "dark_request": False,
                "media": {"media_entities": [], "possibly_sensitive": False},
                "semantic_annotation_ids": [],
            },
            "features": {
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
                "responsive_web_twitter_article_tweet_consumption_enabled": False,
                "responsive_web_media_download_video_enabled": False,
            },
            "queryId": query_id,
        }
        if attachment_url:
            payload["variables"]["attachment_url"] = attachment_url
        if tweet_id_to_reply:
            payload["variables"]["reply"] = {
                "in_reply_to_tweet_id": str(tweet_id_to_reply),
                "exclude_reply_user_ids": [],
            }
        if media_id:
            payload["variables"]["media"]["media_entities"].append(
                {"media_id": str(media_id), "tagged_users": []}
            )

        response, response_json = await self.request("POST", url, json=payload)
        tweet = Tweet.from_raw_data(
            response_json["data"]["create_tweet"]["tweet_results"]["result"]
        )
        return tweet

    async def _tweet_or_search_duplicate(
        self,
        text: str = None,
        *,
        media_id: int | str = None,
        tweet_id_to_reply: str | int = None,
        attachment_url: str = None,
        search_duplicate: bool = True,
    ) -> Tweet:
        try:
            tweet = await self._tweet(
                text,
                media_id=media_id,
                tweet_id_to_reply=tweet_id_to_reply,
                attachment_url=attachment_url,
            )
        except HTTPException as exc:
            if (
                search_duplicate
                and 187 in exc.api_codes  # duplicate tweet (Status is a duplicate)
            ):
                tweets = await self.request_tweets()
                duplicate_tweet = None
                for tweet_ in tweets:
                    if tweet_.text.startswith(text.strip()):
                        duplicate_tweet = tweet_

                if not duplicate_tweet:
                    raise FailedToFindDuplicatePost(
                        f"Couldn't find a post duplicate in the next 20 posts"
                    )
                tweet = duplicate_tweet

            else:
                raise

        return tweet

    async def tweet(
        self,
        text: str,
        *,
        media_id: int | str = None,
        search_duplicate: bool = True,
    ) -> Tweet:
        return await self._tweet_or_search_duplicate(
            text,
            media_id=media_id,
            search_duplicate=search_duplicate,
        )

    async def reply(
        self,
        tweet_id: str | int,
        text: str,
        *,
        media_id: int | str = None,
        search_duplicate: bool = True,
    ) -> Tweet:
        return await self._tweet_or_search_duplicate(
            text,
            media_id=media_id,
            tweet_id_to_reply=tweet_id,
            search_duplicate=search_duplicate,
        )

    async def quote(
        self,
        tweet_url: str,
        text: str,
        *,
        media_id: int | str = None,
        search_duplicate: bool = True,
    ) -> Tweet:
        return await self._tweet_or_search_duplicate(
            text,
            media_id=media_id,
            attachment_url=tweet_url,
            search_duplicate=search_duplicate,
        )

    async def vote(
        self, tweet_id: int | str, card_id: int | str, choice_number: int
    ) -> dict:
        """
        :return: Raw vote information
        """
        url = "https://caps.twitter.com/v2/capi/passthrough/1"
        params = {
            "twitter:string:card_uri": f"card://{card_id}",
            "twitter:long:original_tweet_id": str(tweet_id),
            "twitter:string:response_card_name": "poll2choice_text_only",
            "twitter:string:cards_platform": "Web-12",
            "twitter:string:selected_choice": str(choice_number),
        }
        response, response_json = await self.request("POST", url, params=params)
        return response_json

    async def _request_users(
        self, action: str, user_id: int | str, count: int
    ) -> list[User]:
        url, query_id = self._action_to_url(action)
        variables = {
            "userId": str(user_id),
            "count": count,
            "includePromotedContent": False,
        }
        features = {
            "rweb_lists_timeline_redesign_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": False,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_media_download_video_enabled": False,
            "responsive_web_enhance_cards_enabled": False,
        }
        params = {
            "variables": to_json(variables),
            "features": to_json(features),
        }
        response, response_json = await self.request("GET", url, params=params)

        users = []
        if "result" in response_json["data"]["user"]:
            entries = response_json["data"]["user"]["result"]["timeline"]["timeline"][
                "instructions"
            ][-1]["entries"]
            for entry in entries:
                if entry["entryId"].startswith("user"):
                    user_data_dict = entry["content"]["itemContent"]["user_results"][
                        "result"
                    ]
                    users.append(User.from_raw_data(user_data_dict))
        return users

    async def request_followers(
        self, user_id: int | str = None, count: int = 10
    ) -> list[User]:
        """
        :param user_id: Текущий пользователь, если не передан ID иного пользователя.
        :param count: Количество подписчиков.
        """
        if user_id:
            return await self._request_users("Followers", user_id, count)
        else:
            if not self.account.id:
                await self.request_user()
            return await self._request_users("Followers", self.account.id, count)

    async def request_followings(
        self, user_id: int | str = None, count: int = 10
    ) -> list[User]:
        """
        :param user_id: Текущий пользователь, если не передан ID иного пользователя.
        :param count: Количество подписчиков.
        """
        if user_id:
            return await self._request_users("Following", user_id, count)
        else:
            if not self.account.id:
                await self.request_user()
            return await self._request_users("Following", self.account.id, count)

    async def request_users(
        self, user_ids: Iterable[str | int]
    ) -> dict[int : User | Account]:
        url, query_id = self._action_to_url("UsersByRestIds")
        variables = {"userIds": list({str(user_id) for user_id in user_ids})}
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "verified_phone_label_enabled": False,
        }
        query = {"variables": variables, "features": features}
        response, data = await self.request("GET", url, params=query)

        users = {}
        for user_data in data["data"]["users"]:
            user_data = user_data["result"]
            user = User.from_raw_data(user_data)
            users[user.id] = user
        return users

    async def _request_tweet(self, tweet_id: int | str) -> Tweet:
        url, query_id = self._action_to_url("TweetDetail")
        variables = {
            "focalTweetId": str(tweet_id),
            "with_rux_injections": False,
            "includePromotedContent": True,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        features = {
            "rweb_lists_timeline_redesign_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
        }
        query = {
            "variables": to_json(variables),
            "features": to_json(features),
        }
        response, data = await self.request("GET", url, params=query)
        instructions = data["data"]["threaded_conversation_with_injections_v2"]["instructions"]  # type: ignore
        tweet_data = tweets_data_from_instructions(instructions)[0]
        return Tweet.from_raw_data(tweet_data)

    async def _request_tweets(self, user_id: int | str, count: int = 20) -> list[Tweet]:
        url, query_id = self._action_to_url("UserTweets")
        variables = {
            "userId": str(user_id),
            "count": count,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": False,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_media_download_video_enabled": False,
            "responsive_web_enhance_cards_enabled": False,
        }
        params = {"variables": to_json(variables), "features": to_json(features)}
        response, data = await self.request("GET", url, params=params)

        instructions = data["data"]["user"]["result"]["timeline_v2"]["timeline"][
            "instructions"
        ]
        tweets_data = tweets_data_from_instructions(instructions)
        return [Tweet.from_raw_data(tweet_data) for tweet_data in tweets_data]

    async def request_tweet(self, tweet_id: int | str) -> Tweet:
        return await self._request_tweet(tweet_id)

    async def request_tweets(
        self,
        user_id: int | str = None,
        count: int = 20,
    ) -> list[Tweet]:
        if not user_id:
            if not self.account.id:
                await self.request_user()
            user_id = self.account.id

        return await self._request_tweets(user_id, count)

    async def _update_profile_image(
        self, type: Literal["banner", "image"], media_id: str | int
    ) -> str:
        """
        :return: Image URL
        """
        url = f"https://api.twitter.com/1.1/account/update_profile_{type}.json"
        params = {
            "media_id": str(media_id),
            "include_profile_interstitial_type": "1",
            "include_blocking": "1",
            "include_blocked_by": "1",
            "include_followed_by": "1",
            "include_want_retweets": "1",
            "include_mute_edge": "1",
            "include_can_dm": "1",
            "include_can_media_tag": "1",
            "include_ext_has_nft_avatar": "1",
            "include_ext_is_blue_verified": "1",
            "include_ext_verified_type": "1",
            "include_ext_profile_image_shape": "1",
            "skip_status": "1",
            "return_user": "true",
        }
        response, data = await self.request("POST", url, params=params)
        image_url = data[f"profile_{type}_url"]
        return image_url

    async def update_profile_avatar(self, media_id: int | str) -> str:
        """
        :return: Image URL
        """
        return await self._update_profile_image("image", media_id)

    async def update_profile_banner(self, media_id: int | str) -> str:
        """
        :return: Image URL
        """
        return await self._update_profile_image("banner", media_id)

    async def change_username(self, username: str) -> bool:
        url = "https://twitter.com/i/api/1.1/account/settings.json"
        payload = {"screen_name": username}
        response, data = await self.request("POST", url, data=payload)
        new_username = data["screen_name"]
        changed = new_username == username
        self.account.username = new_username
        return changed

    async def change_password(self, password: str) -> bool:
        """
        После изменения пароля обновляется auth_token!
        """
        if not self.account.password:
            raise ValueError(f"Specify the current password before changing it")

        url = "https://twitter.com/i/api/i/account/change_password.json"
        payload = {
            "current_password": self.account.password,
            "password": password,
            "password_confirmation": password,
        }
        response, data = await self.request("POST", url, data=payload)
        changed = data["status"] == "ok"
        # TODO Делать это автоматически в методе request
        auth_token = response.cookies.get("auth_token", domain=".twitter.com")
        self.account.auth_token = auth_token
        self.account.password = password
        return changed

    async def update_profile(
        self,
        name: str = None,
        description: str = None,
        location: str = None,
        website: str = None,
    ) -> bool:
        """
        Locks an account!
        """
        if name is None and description is None:
            raise ValueError("Specify at least one param")

        url = "https://twitter.com/i/api/1.1/account/update_profile.json"
        # headers = {"content-type": "application/x-www-form-urlencoded"}
        # Создаем словарь data, включая в него только те ключи, для которых значения не равны None
        payload = {
            k: v
            for k, v in [
                ("name", name),
                ("description", description),
                ("location", location),
                ("url", website),
            ]
            if v is not None
        }
        # response, response_json = await self.request("POST", url, headers=headers, data=payload)
        response, data = await self.request("POST", url, data=payload)
        # Проверяем, что все переданные параметры соответствуют полученным
        updated = all(
            data.get(key) == value for key, value in payload.items() if key != "url"
        )
        if website:
            updated &= URL(website) == URL(
                data["entities"]["url"]["urls"][0]["expanded_url"]
            )
        await self.request_user()
        return updated

    async def establish_status(self):
        url = "https://twitter.com/i/api/1.1/account/update_profile.json"
        try:
            await self.request("POST", url)
        except BadAccount:
            pass

    async def update_birthdate(
        self,
        day: int,
        month: int,
        year: int,
        visibility: Literal["self", "mutualfollow"] = "self",
        year_visibility: Literal["self"] = "self",
    ) -> bool:
        url = "https://twitter.com/i/api/1.1/account/update_profile.json"
        headers = {"content-type": "application/x-www-form-urlencoded"}
        data = {
            "birthdate_day": day,
            "birthdate_month": month,
            "birthdate_year": year,
            "birthdate_visibility": visibility,
            "birthdate_year_visibility": year_visibility,
        }
        response, response_json = await self.request(
            "POST", url, headers=headers, data=data
        )
        birthdate_data = response_json["extended_profile"]["birthdate"]
        updated = all(
            (
                birthdate_data["day"] == day,
                birthdate_data["month"] == month,
                birthdate_data["year"] == year,
                birthdate_data["visibility"] == visibility,
                birthdate_data["year_visibility"] == year_visibility,
            )
        )
        return updated

    async def send_message(self, user_id: int | str, text: str) -> dict:
        """
        :return: Event data
        """
        url = "https://api.twitter.com/1.1/direct_messages/events/new.json"
        payload = {
            "event": {
                "type": "message_create",
                "message_create": {
                    "target": {"recipient_id": user_id},
                    "message_data": {"text": text},
                },
            }
        }
        response, data = await self.request("POST", url, json=payload)
        event_data = data["event"]
        return event_data  # TODO Возвращать модель, а не словарь

    async def request_messages(self) -> list[dict]:
        """
        :return: Messages data
        """
        url = "https://twitter.com/i/api/1.1/dm/inbox_initial_state.json"
        params = {
            "nsfw_filtering_enabled": "false",
            "filter_low_quality": "false",
            "include_quality": "all",
            "include_profile_interstitial_type": "1",
            "include_blocking": "1",
            "include_blocked_by": "1",
            "include_followed_by": "1",
            "include_want_retweets": "1",
            "include_mute_edge": "1",
            "include_can_dm": "1",
            "include_can_media_tag": "1",
            "include_ext_has_nft_avatar": "1",
            "include_ext_is_blue_verified": "1",
            "include_ext_verified_type": "1",
            "include_ext_profile_image_shape": "1",
            "skip_status": "1",
            "dm_secret_conversations_enabled": "false",
            "krs_registration_enabled": "true",
            "cards_platform": "Web-12",
            "include_cards": "1",
            "include_ext_alt_text": "true",
            "include_ext_limited_action_results": "true",
            "include_quote_count": "true",
            "include_reply_count": "1",
            "tweet_mode": "extended",
            "include_ext_views": "true",
            "dm_users": "true",
            "include_groups": "true",
            "include_inbox_timelines": "true",
            "include_ext_media_color": "true",
            "supports_reactions": "true",
            "include_ext_edit_control": "true",
            "include_ext_business_affiliations_label": "true",
            "ext": "mediaColor,altText,mediaStats,highlightedLabel,hasNftAvatar,voiceInfo,birdwatchPivot,superFollowMetadata,unmentionInfo,editControl",
        }
        response, response_json = await self.request("GET", url, params=params)
        messages = [
            entry["message"]
            for entry in response_json["inbox_initial_state"]["entries"]
            if "message" in entry
        ]
        return messages  # TODO Возвращать модели, а не словари

    async def _confirm_unlock(
        self,
        authenticity_token: str,
        assignment_token: str,
        verification_string: str = None,
    ) -> tuple[requests.Response, str]:
        payload = {
            "authenticity_token": authenticity_token,
            "assignment_token": assignment_token,
            "lang": "en",
            "flow": "",
        }
        if verification_string:
            payload["verification_string"] = verification_string
            payload["language_code"] = "en"

        return await self.request("POST", self._CAPTCHA_URL, data=payload, bearer=False)

    async def unlock(self):
        if not self.account.status == "LOCKED":
            return

        response, html = await self.request("GET", self._CAPTCHA_URL, bearer=False)
        (
            authenticity_token,
            assignment_token,
            needs_unlock,
            start_button,
            finish_button,
        ) = parse_unlock_html(html)
        attempt = 1

        if start_button or finish_button:
            response, html = await self._confirm_unlock(
                authenticity_token, assignment_token
            )
            (
                authenticity_token,
                assignment_token,
                needs_unlock,
                start_button,
                finish_button,
            ) = parse_unlock_html(html)

        funcaptcha = {
            "api_key": self.capsolver_api_key,
            "websiteURL": self._CAPTCHA_URL,
            "websitePublicKey": self._CAPTCHA_SITE_KEY,
        }
        if self._session.proxy is not None:
            funcaptcha["captcha_type"] = FunCaptchaTypeEnm.FunCaptchaTask
            funcaptcha["proxyType"] = self._session.proxy.protocol
            funcaptcha["proxyAddress"] = self._session.proxy.host
            funcaptcha["proxyPort"] = self._session.proxy.port
            funcaptcha["proxyLogin"] = self._session.proxy.login
            funcaptcha["proxyPassword"] = self._session.proxy.password
        else:
            funcaptcha["captcha_type"] = FunCaptchaTypeEnm.FunCaptchaTaskProxyLess

        while needs_unlock:
            solution = await FunCaptcha(**funcaptcha).aio_captcha_handler()
            token = solution.solution["token"]
            response, html = await self._confirm_unlock(
                authenticity_token,
                assignment_token,
                verification_string=token,
            )

            if (
                attempt > self.max_unlock_attempts
                or response.url == "https://twitter.com/?lang=en"
            ):
                await self.establish_status()
                return

            (
                authenticity_token,
                assignment_token,
                needs_unlock,
                start_button,
                finish_button,
            ) = parse_unlock_html(html)

            if finish_button:
                response, html = await self._confirm_unlock(
                    authenticity_token, assignment_token
                )
                (
                    authenticity_token,
                    assignment_token,
                    needs_unlock,
                    start_button,
                    finish_button,
                ) = parse_unlock_html(html)

            attempt += 1

    async def _task(self, **kwargs):
        """
        :return: flow_token, subtasks
        """
        url = "https://api.twitter.com/1.1/onboarding/task.json"
        response, response_json = await self.request("POST", url, **kwargs)
        return response_json["flow_token"], response_json["subtasks"]

    async def _request_login_tasks(self):
        """
        :return: flow_token, subtask_ids
        """
        params = {
            "flow_name": "login",
        }
        payload = {
            "input_flow_data": {
                "flow_context": {
                    "debug_overrides": {},
                    "start_location": {"location": "splash_screen"},
                }
            },
            "subtask_versions": {
                "action_list": 2,
                "alert_dialog": 1,
                "app_download_cta": 1,
                "check_logged_in_account": 1,
                "choice_selection": 3,
                "contacts_live_sync_permission_prompt": 0,
                "cta": 7,
                "email_verification": 2,
                "end_flow": 1,
                "enter_date": 1,
                "enter_email": 2,
                "enter_password": 5,
                "enter_phone": 2,
                "enter_recaptcha": 1,
                "enter_text": 5,
                "enter_username": 2,
                "generic_urt": 3,
                "in_app_notification": 1,
                "interest_picker": 3,
                "js_instrumentation": 1,
                "menu_dialog": 1,
                "notifications_permission_prompt": 2,
                "open_account": 2,
                "open_home_timeline": 1,
                "open_link": 1,
                "phone_verification": 4,
                "privacy_options": 1,
                "security_key": 3,
                "select_avatar": 4,
                "select_banner": 2,
                "settings_list": 7,
                "show_code": 1,
                "sign_up": 2,
                "sign_up_review": 4,
                "tweet_selection_urt": 1,
                "update_users": 1,
                "upload_media": 1,
                "user_recommendations_list": 4,
                "user_recommendations_urt": 1,
                "wait_spinner": 3,
                "web_modal": 1,
            },
        }
        return await self._task(params=params, json=payload, auth=False)

    async def _send_task(self, flow_token: str, subtask_inputs: list[dict], **kwargs):
        payload = kwargs["json"] = kwargs.get("json") or {}
        payload.update(
            {
                "flow_token": flow_token,
                "subtask_inputs": subtask_inputs,
            }
        )
        return await self._task(**kwargs)

    async def _finish_task(self, flow_token):
        payload = {
            "flow_token": flow_token,
            "subtask_inputs": [],
        }
        return await self._task(json=payload)

    async def _login_enter_user_identifier(self, flow_token):
        subtask_inputs = [
            {
                "subtask_id": "LoginEnterUserIdentifierSSO",
                "settings_list": {
                    "setting_responses": [
                        {
                            "key": "user_identifier",
                            "response_data": {
                                "text_data": {
                                    "result": self.account.email
                                    or self.account.username
                                }
                            },
                        }
                    ],
                    "link": "next_link",
                },
            }
        ]
        return await self._send_task(flow_token, subtask_inputs, auth=False)

    async def _login_enter_password(self, flow_token):
        subtask_inputs = [
            {
                "subtask_id": "LoginEnterPassword",
                "enter_password": {
                    "password": self.account.password,
                    "link": "next_link",
                },
            }
        ]
        return await self._send_task(flow_token, subtask_inputs, auth=False)

    async def _account_duplication_check(self, flow_token):
        subtask_inputs = [
            {
                "subtask_id": "AccountDuplicationCheck",
                "check_logged_in_account": {"link": "AccountDuplicationCheck_false"},
            }
        ]
        return await self._send_task(flow_token, subtask_inputs, auth=False)

    async def _login_two_factor_auth_challenge(self, flow_token):
        if not self.account.totp_secret:
            raise TwitterException(
                f"Failed to login. Task id: LoginTwoFactorAuthChallenge"
            )

        subtask_inputs = [
            {
                "subtask_id": "LoginTwoFactorAuthChallenge",
                "enter_text": {
                    "text": self.account.get_totp_code(),
                    "link": "next_link",
                },
            }
        ]
        return await self._send_task(flow_token, subtask_inputs, auth=False)

    async def _viewer(self):
        url, query_id = self._action_to_url("Viewer")
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        field_toggles = {
            "isDelegate": False,
            "withAuxiliaryUserLabels": False,
        }
        variables = {"withCommunitiesMemberships": True}
        params = {
            "features": to_json(features),
            "fieldToggles": to_json(field_toggles),
            "variables": to_json(variables),
        }
        return self.request("GET", url, params=params)

    async def _request_guest_token(self) -> str:
        """
        Помимо запроса guest_token также устанавливает в сессию guest_id cookie

        :return: guest_token
        """
        url = "https://twitter.com"
        response = await self._session.request("GET", url)
        # TODO Если в сессии есть рабочий auth_token, то не вернет нужную страницу.
        #   Поэтому нужно очищать сессию перед вызовом этого метода.
        guest_token = re.search(r"gt\s?=\s?\d+", response.text)[0].split("=")[1]
        return guest_token

    async def _login(self):
        guest_token = await self._request_guest_token()
        self._session.headers["X-Guest-Token"] = guest_token

        # Можно не устанавливать, так как твиттер сам вернет этот токен
        # self._session.cookies["gt"] = guest_token

        flow_token, subtasks = await self._request_login_tasks()
        for _ in range(2):
            flow_token, subtasks = await self._login_enter_user_identifier(flow_token)
        flow_token, subtasks = await self._login_enter_password(flow_token)
        flow_token, subtasks = await self._account_duplication_check(flow_token)

        subtask_ids = [subtask["subtask_id"] for subtask in subtasks]

        # TODO IMAP Обработчик
        if "LoginAcid" in subtask_ids:
            raise TwitterException(f"Failed to login: email verification!")

        if "LoginTwoFactorAuthChallenge" in subtask_ids:
            flow_token, subtasks = await self._login_two_factor_auth_challenge(
                flow_token
            )

        # TODO Делать это автоматически в методе request
        self.account.auth_token = self._session.cookies["auth_token"]
        self.account.ct0 = self._session.cookies["ct0"]

        await self._finish_task(flow_token)

    async def login(self):
        if self.account.auth_token:
            await self.establish_status()
            if self.account.status != "BAD_TOKEN":
                return

        if not self.account.email and not self.account.username:
            raise ValueError("No email or username")

        if not self.account.password:
            raise ValueError("No password")

        await self._login()
        await self.establish_status()

    async def totp_is_enabled(self):
        if not self.account.id:
            await self.request_user()

        url = f"https://twitter.com/i/api/1.1/strato/column/User/{self.account.id}/account-security/twoFactorAuthSettings2"
        response, data = await self.request("GET", url)
        return "Totp" in [
            method_data["twoFactorType"] for method_data in data["methods"]
        ]

    async def _request_2fa_tasks(self):
        """
        :return: flow_token, subtask_ids
        """
        params = {
            "flow_name": "two-factor-auth-app-enrollment",
        }
        payload = {
            "input_flow_data": {
                "flow_context": {
                    "debug_overrides": {},
                    "start_location": {"location": "settings"},
                }
            },
            "subtask_versions": {
                "action_list": 2,
                "alert_dialog": 1,
                "app_download_cta": 1,
                "check_logged_in_account": 1,
                "choice_selection": 3,
                "contacts_live_sync_permission_prompt": 0,
                "cta": 7,
                "email_verification": 2,
                "end_flow": 1,
                "enter_date": 1,
                "enter_email": 2,
                "enter_password": 5,
                "enter_phone": 2,
                "enter_recaptcha": 1,
                "enter_text": 5,
                "enter_username": 2,
                "generic_urt": 3,
                "in_app_notification": 1,
                "interest_picker": 3,
                "js_instrumentation": 1,
                "menu_dialog": 1,
                "notifications_permission_prompt": 2,
                "open_account": 2,
                "open_home_timeline": 1,
                "open_link": 1,
                "phone_verification": 4,
                "privacy_options": 1,
                "security_key": 3,
                "select_avatar": 4,
                "select_banner": 2,
                "settings_list": 7,
                "show_code": 1,
                "sign_up": 2,
                "sign_up_review": 4,
                "tweet_selection_urt": 1,
                "update_users": 1,
                "upload_media": 1,
                "user_recommendations_list": 4,
                "user_recommendations_urt": 1,
                "wait_spinner": 3,
                "web_modal": 1,
            },
        }
        return await self._task(params=params, json=payload)

    async def _two_factor_enrollment_verify_password_subtask(self, flow_token: str):
        subtask_inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentVerifyPasswordSubtask",
                "enter_password": {
                    "password": self.account.password,
                    "link": "next_link",
                },
            }
        ]
        return await self._send_task(flow_token, subtask_inputs)

    async def _two_factor_enrollment_authentication_app_begin_subtask(
        self, flow_token: str
    ):
        subtask_inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppBeginSubtask",
                "action_list": {"link": "next_link"},
            }
        ]
        return await self._send_task(flow_token, subtask_inputs)

    async def _two_factor_enrollment_authentication_app_plain_code_subtask(
        self, flow_token: str
    ):
        subtask_inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppPlainCodeSubtask",
                "show_code": {"link": "next_link"},
            },
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppEnterCodeSubtask",
                "enter_text": {
                    "text": self.account.get_totp_code(),
                    "link": "next_link",
                },
            },
        ]
        return await self._send_task(flow_token, subtask_inputs)

    async def _finish_2fa_task(self, flow_token: str):
        subtask_inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppCompleteSubtask",
                "cta": {"link": "finish_link"},
            }
        ]
        return await self._send_task(flow_token, subtask_inputs)

    async def _enable_totp(self):
        flow_token, subtasks = await self._request_2fa_tasks()
        flow_token, subtasks = (
            await self._two_factor_enrollment_verify_password_subtask(flow_token)
        )
        flow_token, subtasks = (
            await self._two_factor_enrollment_authentication_app_begin_subtask(
                flow_token
            )
        )

        for subtask in subtasks:
            if (
                subtask["subtask_id"]
                == "TwoFactorEnrollmentAuthenticationAppPlainCodeSubtask"
            ):
                self.account.totp_secret = subtask["show_code"]["code"]
                break

        flow_token, subtasks = (
            await self._two_factor_enrollment_authentication_app_plain_code_subtask(
                flow_token
            )
        )

        for subtask in subtasks:
            if (
                subtask["subtask_id"]
                == "TwoFactorEnrollmentAuthenticationAppCompleteSubtask"
            ):
                result = re.search(
                    r"\n[a-z0-9]{12}\n", subtask["cta"]["secondary_text"]["text"]
                )
                backup_code = result[0].strip() if result else None
                self.account.backup_code = backup_code
                break

        await self._finish_2fa_task(flow_token)

    async def enable_totp(self):
        if not self.account.password:
            raise ValueError("Password is required for this action")

        if await self.totp_is_enabled():
            return

        # TODO Осторожно, костыль! Перед началом работы вызываем request_user_data, чтоб убедиться что нет других ошибок
        await self.request_user()
        await self._enable_totp()
