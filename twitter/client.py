from typing import Any, Literal, Iterable
from time import time
import asyncio
import base64
import json
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
    BadAccountToken,
    AccountLocked,
    AccountConsentLocked,
    AccountSuspended,
    AccountNotFound,
)
from .base import BaseHTTPClient
from .account import Account, AccountStatus
from .models import User, Tweet, Media, Subtask
from .utils import (
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
        "x-twitter-client-language": "en",
    }
    _GRAPHQL_URL = "https://twitter.com/i/api/graphql"
    _ACTION_TO_QUERY_ID = {
        "CreateRetweet": "ojPdsZsimiJrUGLR1sjUtA",
        "FavoriteTweet": "lI07N6Otwv1PhnEgXILM7A",
        "UnfavoriteTweet": "ZYKSe-w7KEslx3JhSIk5LA",
        "CreateTweet": "v0en1yVV-Ybeek8ClmXwYw",
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
        auto_relogin: bool = True,
        update_account_info_on_startup: bool = True,
        **session_kwargs,
    ):
        super().__init__(**session_kwargs)
        self.account = account
        self.wait_on_rate_limit = wait_on_rate_limit
        self.capsolver_api_key = capsolver_api_key
        self.max_unlock_attempts = max_unlock_attempts
        self.auto_relogin = auto_relogin
        self._update_account_info_on_startup = update_account_info_on_startup

        self.gql = GQLClient(self)

    async def __aenter__(self):
        await self.on_startup()
        return await super().__aenter__()

    async def _request(
        self,
        method,
        url,
        *,
        auth: bool = True,
        bearer: bool = True,
        wait_on_rate_limit: bool = None,
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
            headers["x-twitter-auth-type"] = "OAuth2Session"
            if self.account.ct0:
                cookies["ct0"] = self.account.ct0
                headers["x-csrf-token"] = self.account.ct0
        else:
            if "auth_token" in cookies:
                del cookies["auth_token"]
            if "x-twitter-auth-type" in headers:
                del headers["x-twitter-auth-type"]

        # fmt: off
        log_message = (f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                       f" ==> Request {method} {url}")
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
        logger.debug(f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                     f" <== Response {method} {url}"
                     f"\nStatus code: {response.status_code}"
                     f"\nResponse data: {data}")
        # fmt: on

        if ct0 := self._session.cookies.get("ct0", domain=".twitter.com"):
            self.account.ct0 = ct0

        auth_token = self._session.cookies.get("auth_token")
        if auth_token and auth_token != self.account.auth_token:
            self.account.auth_token = auth_token
            logger.warning(
                f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                f" Requested new auth_token!"
            )

        try:
            data = response.json()
        except json.decoder.JSONDecodeError:
            pass

        if 300 > response.status_code >= 200:
            if isinstance(data, dict) and "errors" in data:
                exc = HTTPException(response, data)

                if 141 in exc.api_codes or 37 in exc.api_codes:
                    self.account.status = AccountStatus.SUSPENDED
                    raise AccountSuspended(exc, self.account)

                if 326 in exc.api_codes:
                    for error_data in exc.api_errors:
                        if (
                            error_data.get("code") == 326
                            and error_data.get("bounce_location")
                            == "/i/flow/consent_flow"
                        ):
                            self.account.status = AccountStatus.CONSENT_LOCKED
                            raise AccountConsentLocked(exc, self.account)

                    self.account.status = AccountStatus.LOCKED
                    raise AccountLocked(exc, self.account)
                raise exc

            return response, data

        if response.status_code == 400:
            exc = BadRequest(response, data)

            if 399 in exc.api_codes:
                self.account.status = AccountStatus.NOT_FOUND
                raise AccountNotFound(exc, self.account)

            raise exc

        if response.status_code == 401:
            exc = Unauthorized(response, data)

            if 32 in exc.api_codes:
                self.account.status = AccountStatus.BAD_TOKEN
                raise BadAccountToken(exc, self.account)

            raise exc

        if response.status_code == 403:
            exc = Forbidden(response, data)

            if 64 in exc.api_codes:
                self.account.status = AccountStatus.SUSPENDED
                raise AccountSuspended(exc, self.account)

            if 326 in exc.api_codes:
                for error_data in exc.api_errors:
                    if (
                        error_data.get("code") == 326
                        and error_data.get("bounce_location") == "/i/flow/consent_flow"
                    ):
                        self.account.status = AccountStatus.CONSENT_LOCKED
                        raise AccountConsentLocked(exc, self.account)

                self.account.status = AccountStatus.LOCKED
                raise AccountLocked(exc, self.account)

            raise exc

        if response.status_code == 404:
            raise NotFound(response, data)

        if response.status_code == 429:
            if wait_on_rate_limit is None:
                wait_on_rate_limit = self.wait_on_rate_limit
            if not wait_on_rate_limit:
                raise RateLimited(response, data)

            reset_time = int(response.headers["x-rate-limit-reset"])
            sleep_time = reset_time - int(time()) + 1
            if sleep_time > 0:
                logger.warning(
                    f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                    f"Rate limited! Sleep time: {sleep_time} sec."
                )
                await asyncio.sleep(sleep_time)
            return await self._request(
                method,
                url,
                auth=auth,
                bearer=bearer,
                wait_on_rate_limit=wait_on_rate_limit,
                **kwargs,
            )

        if response.status_code >= 500:
            raise ServerError(response, data)

    async def request(
        self,
        method,
        url,
        *,
        auto_unlock: bool = True,
        auto_relogin: bool = None,
        rerequest_on_bad_ct0: bool = True,
        **kwargs,
    ) -> tuple[requests.Response, Any]:
        try:
            return await self._request(method, url, **kwargs)

        except AccountLocked:
            if not self.capsolver_api_key or not auto_unlock:
                raise

            await self.unlock()
            return await self._request(method, url, **kwargs)

        except BadAccountToken:
            if auto_relogin is None:
                auto_relogin = self.auto_relogin
            if (
                not auto_relogin
                or not self.account.password
                or not (self.account.email or self.account.username)
            ):
                raise

            await self.relogin()
            return await self.request(method, url, auto_relogin=False, **kwargs)

        except Forbidden as exc:
            if (
                rerequest_on_bad_ct0
                and 353 in exc.api_codes
                and "ct0" in exc.response.cookies
            ):
                return await self.request(
                    method, url, rerequest_on_bad_ct0=False, **kwargs
                )
            else:
                raise

    async def on_startup(self):
        if self._update_account_info_on_startup:
            await self.update_account_info()
            await self.establish_status()

    async def _request_oauth2_auth_code(
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

    async def _confirm_oauth2(self, auth_code: str):
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

    async def oauth2(
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
        :param state: Уникальная строка состояния для предотвращения CSRF-атак.
        :param redirect_uri: URI перенаправления, на который будет отправлен ответ.
        :param scope: Строка областей доступа, запрашиваемых у пользователя.
        :param response_type: Тип ответа, который ожидается от сервера авторизации.
        :return: Код авторизации (привязки).
        """
        auth_code = await self._request_oauth2_auth_code(
            client_id,
            code_challenge,
            state,
            redirect_uri,
            code_challenge_method,
            scope,
            response_type,
        )
        await self._confirm_oauth2(auth_code)
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

    async def _update_account_username(self):
        url = "https://twitter.com/i/api/1.1/account/settings.json"
        response, response_json = await self.request("POST", url)
        self.account.username = response_json["screen_name"]

    async def _request_user_by_username(self, username: str) -> User | None:
        url, query_id = self._action_to_url("UserByScreenName")
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
            "variables": variables,
            "features": features,
            "fieldToggles": field_toggles,
        }
        response, data = await self.request("GET", url, params=params)
        if not data["data"]:
            return None
        return User.from_raw_data(data["data"]["user"]["result"])

    async def request_user_by_username(self, username: str) -> User | Account | None:
        """
        :param username: Имя пользователя без знака `@`
        :return: Пользователь, если существует, иначе None. Или собственный аккаунт, если совпадает имя пользователя.
        """
        if not self.account.username:
            await self.update_account_info()

        user = await self._request_user_by_username(username)

        if user and user.username == self.account.username:
            self.account.update(**user.model_dump())
            return self.account

        return user

    async def _request_users_by_ids(
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
            if user.id == self.account.id:
                users[self.account.id] = self.account
        return users

    async def request_user_by_id(self, user_id: int | str) -> User | Account | None:
        """
        :param user_id: ID пользователя
        :return: Пользователь, если существует, иначе None. Или собственный аккаунт, если совпадает ID.
        """
        if not self.account.id:
            await self.update_account_info()

        users = await self._request_users_by_ids((user_id,))
        user = users[user_id]
        return user

    async def request_users_by_ids(
        self, user_ids: Iterable[str | int]
    ) -> dict[int : User | Account]:
        """
        :param user_ids: ID пользователей
        :return: Пользователи, если существует, иначе None. Или собственный аккаунт, если совпадает ID.
        """
        return await self._request_users_by_ids(user_ids)

    async def update_account_info(self):
        if not self.account.username:
            await self._update_account_username()

        await self.request_user_by_username(self.account.username)

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
                return Media(**data)
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

        Иногда может вернуть ошибку 404 (Not Found), если плохой прокси или по другим неизвестным причинам

        :return: Tweet
        """
        return await self._repost_or_search_duplicate(
            tweet_id, search_duplicate=search_duplicate
        )

    async def like(self, tweet_id: int) -> bool:
        """
        :return: Liked or not
        """
        try:
            response_json = await self._interact_with_tweet("FavoriteTweet", tweet_id)
        except HTTPException as exc:
            if 139 in exc.api_codes:
                # Already liked
                return True
            else:
                raise
        return response_json["data"]["favorite_tweet"] == "Done"

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
        variables = {
            "tweet_text": text if text is not None else "",
            "dark_request": False,
            "media": {"media_entities": [], "possibly_sensitive": False},
            "semantic_annotation_ids": [],
        }
        if attachment_url:
            variables["attachment_url"] = attachment_url
        if tweet_id_to_reply:
            variables["reply"] = {
                "in_reply_to_tweet_id": str(tweet_id_to_reply),
                "exclude_reply_user_ids": [],
            }
        if media_id:
            variables["media"]["media_entities"].append(
                {"media_id": str(media_id), "tagged_users": []}
            )
        features = {
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
        }
        payload = {
            "variables": variables,
            "features": features,
            "queryId": query_id,
        }
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
        """
        Иногда может вернуть ошибку 404 (Not Found), если плохой прокси или по другим неизвестным причинам

        :return: Tweet
        """
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
        """
        Иногда может вернуть ошибку 404 (Not Found), если плохой прокси или по другим неизвестным причинам

        :return: Tweet
        """
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
        """
        Иногда может вернуть ошибку 404 (Not Found), если плохой прокси или по другим неизвестным причинам

        :return: Tweet
        """
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

    async def _request_users_by_action(
        self,
        action: str,
        user_id: int | str,
        count: int,
        cursor: str = None,
    ) -> list[User]:
        url, query_id = self._action_to_url(action)
        variables = {
            "userId": str(user_id),
            "count": count,
            "includePromotedContent": False,
        }
        if cursor:
            variables["cursor"] = cursor
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
            "variables": variables,
            "features": features,
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
        self,
        user_id: int | str = None,
        count: int = 20,
        cursor: str = None,
    ) -> list[User]:
        """
        :param user_id: Текущий пользователь, если не передан ID иного пользователя.
        :param count: Количество подписчиков.
        """
        if user_id:
            return await self._request_users_by_action(
                "Followers", user_id, count, cursor
            )
        else:
            if not self.account.id:
                await self.update_account_info()
            return await self._request_users_by_action(
                "Followers", self.account.id, count, cursor
            )

    async def request_followings(
        self,
        user_id: int | str = None,
        count: int = 20,
        cursor: str = None,
    ) -> list[User]:
        """
        :param user_id: Текущий пользователь, если не передан ID иного пользователя.
        :param count: Количество подписчиков.
        """
        if user_id:
            return await self._request_users_by_action(
                "Following", user_id, count, cursor
            )
        else:
            if not self.account.id:
                await self.update_account_info()
            return await self._request_users_by_action(
                "Following", self.account.id, count, cursor
            )

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
            "variables": variables,
            "features": features,
        }
        response, data = await self.request("GET", url, params=query)
        instructions = data["data"]["threaded_conversation_with_injections_v2"]["instructions"]  # type: ignore
        tweet_data = tweets_data_from_instructions(instructions)[0]
        return Tweet.from_raw_data(tweet_data)

    async def _request_tweets(
        self, user_id: int | str, count: int = 20, cursor: str = None
    ) -> list[Tweet]:
        url, query_id = self._action_to_url("UserTweets")
        variables = {
            "userId": str(user_id),
            "count": count,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        if cursor:
            variables["cursor"] = cursor
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
        params = {"variables": variables, "features": features}
        response, data = await self.request("GET", url, params=params)

        instructions = data["data"]["user"]["result"]["timeline_v2"]["timeline"][
            "instructions"
        ]
        tweets_data = tweets_data_from_instructions(instructions)
        return [Tweet.from_raw_data(tweet_data) for tweet_data in tweets_data]

    async def request_tweet(self, tweet_id: int | str) -> Tweet:
        return await self._request_tweet(tweet_id)

    async def request_tweets(
        self, user_id: int | str = None, count: int = 20, cursor: str = None
    ) -> list[Tweet]:
        if not user_id:
            if not self.account.id:
                await self.update_account_info()
            user_id = self.account.id

        return await self._request_tweets(user_id, count, cursor)

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
        response, data = await self.request("POST", url, data=payload)
        # Проверяем, что все переданные параметры соответствуют полученным
        updated = all(
            data.get(key) == value for key, value in payload.items() if key != "url"
        )
        if website:
            updated &= URL(website) == URL(
                data["entities"]["url"]["urls"][0]["expanded_url"]
            )
        await self.update_account_info()
        return updated

    async def establish_status(self):
        url = "https://twitter.com/i/api/1.1/account/update_profile.json"
        try:
            await self.request("POST", url, auto_unlock=False, auto_relogin=False)
            self.account.status = AccountStatus.GOOD
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
        payload = {
            "birthdate_day": day,
            "birthdate_month": month,
            "birthdate_year": year,
            "birthdate_visibility": visibility,
            "birthdate_year_visibility": year_visibility,
        }
        response, response_json = await self.request("POST", url, json=payload)
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

    async def send_message_to_conversation(
        self, conversation_id: int | str, text: str
    ) -> dict:
        """
        requires OAuth1 or OAuth2

        :return: Event data
        """
        url = f"https://api.twitter.com/2/dm_conversations/{conversation_id}/messages"
        payload = {"text": text}
        response, response_json = await self.request("POST", url, json=payload)
        event_data = response_json["event"]
        return event_data

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

        # TODO ui_metrics

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
            delete_button,
        ) = parse_unlock_html(html)
        attempt = 1

        if delete_button:
            response, html = await self._confirm_unlock(
                authenticity_token, assignment_token
            )
            (
                authenticity_token,
                assignment_token,
                needs_unlock,
                start_button,
                finish_button,
                delete_button,
            ) = parse_unlock_html(html)

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
                delete_button,
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

        while needs_unlock and attempt <= self.max_unlock_attempts:
            solution = await FunCaptcha(**funcaptcha).aio_captcha_handler()
            if solution.errorId:
                logger.warning(
                    f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                    f"Failed to solve funcaptcha:"
                    f"\n\tUnlock attempt: {attempt}/{self.max_unlock_attempts}"
                    f"\n\tError ID: {solution.errorId}"
                    f"\n\tError code: {solution.errorCode}"
                    f"\n\tError description: {solution.errorDescription}"
                )
                attempt += 1
                continue

            token = solution.solution["token"]
            response, html = await self._confirm_unlock(
                authenticity_token,
                assignment_token,
                verification_string=token,
            )

            if response.url == "https://twitter.com/?lang=en":
                break

            (
                authenticity_token,
                assignment_token,
                needs_unlock,
                start_button,
                finish_button,
                delete_button,
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
                    delete_button,
                ) = parse_unlock_html(html)

            attempt += 1

        await self.establish_status()

    async def update_backup_code(self):
        url = "https://api.twitter.com/1.1/account/backup_code.json"
        response, response_json = await self.request("GET", url)
        self.account.backup_code = response_json["codes"][0]

    async def _send_raw_subtask(self, **request_kwargs) -> tuple[str, list[Subtask]]:
        """
        :return: flow_token and subtasks
        """
        url = "https://api.twitter.com/1.1/onboarding/task.json"
        response, data = await self.request("POST", url, **request_kwargs)
        subtasks = [
            Subtask.from_raw_data(subtask_data) for subtask_data in data["subtasks"]
        ]
        log_message = (
            f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
            f" Requested subtasks:"
        )
        for subtask in subtasks:
            log_message += f"\n\t{subtask.id}"
            if subtask.primary_text:
                log_message += f"\n\tPrimary text: {subtask.primary_text}"
            if subtask.secondary_text:
                log_message += f"\n\tSecondary text: {subtask.secondary_text}"
            if subtask.detail_text:
                log_message += f"\n\tDetail text: {subtask.detail_text}"
        logger.debug(log_message)
        return data["flow_token"], subtasks

    async def _complete_subtask(
        self,
        flow_token: str,
        inputs: list[dict],
        **request_kwargs,
    ) -> tuple[str, list[Subtask]]:
        payload = request_kwargs["json"] = request_kwargs.get("json") or {}
        payload.update(
            {
                "flow_token": flow_token,
                "subtask_inputs": inputs,
            }
        )
        return await self._send_raw_subtask(**request_kwargs)

    async def _request_login_tasks(self) -> tuple[str, list[Subtask]]:
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
        return await self._send_raw_subtask(params=params, json=payload, auth=False)

    async def _login_enter_user_identifier(self, flow_token: str):
        inputs = [
            {
                "subtask_id": "LoginEnterUserIdentifierSSO",
                "settings_list": {
                    "link": "next_link",
                    "setting_responses": [
                        {
                            "key": "user_identifier",
                            "response_data": {
                                "text_data": {
                                    "result": self.account.username
                                    or self.account.email
                                }
                            },
                        }
                    ],
                },
            }
        ]
        return await self._complete_subtask(flow_token, inputs, auth=False)

    async def _login_enter_password(self, flow_token: str):
        inputs = [
            {
                "subtask_id": "LoginEnterPassword",
                "enter_password": {
                    "link": "next_link",
                    "password": self.account.password,
                },
            }
        ]
        return await self._complete_subtask(flow_token, inputs, auth=False)

    async def _account_duplication_check(self, flow_token):
        inputs = [
            {
                "subtask_id": "AccountDuplicationCheck",
                "check_logged_in_account": {"link": "AccountDuplicationCheck_false"},
            }
        ]
        return await self._complete_subtask(flow_token, inputs, auth=False)

    async def _login_two_factor_auth_challenge(self, flow_token, value: str):
        inputs = [
            {
                "subtask_id": "LoginTwoFactorAuthChallenge",
                "enter_text": {
                    "link": "next_link",
                    "text": value,
                },
            }
        ]
        return await self._complete_subtask(flow_token, inputs, auth=False)

    async def _login_two_factor_auth_choose_method(
        self, flow_token: str, choices: Iterable[int] = (0,)
    ):
        inputs = [
            {
                "subtask_id": "LoginTwoFactorAuthChooseMethod",
                "choice_selection": {
                    "link": "next_link",
                    "selected_choices": [str(choice) for choice in choices],
                },
            }
        ]
        return await self._complete_subtask(flow_token, inputs, auth=False)

    async def _login_acid(
        self,
        flow_token: str,
        value: str,
    ):
        inputs = [
            {
                "subtask_id": "LoginAcid",
                "enter_text": {"text": value, "link": "next_link"},
            }
        ]
        return await self._complete_subtask(flow_token, inputs, auth=False)

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
            "features": features,
            "fieldToggles": field_toggles,
            "variables": variables,
        }
        return await self.request("GET", url, params=params)

    async def _request_guest_token(self) -> str:
        """
        Помимо запроса guest_token также устанавливает в сессию guest_id cookie

        :return: guest_token
        """
        response, data = await self._request(
            "POST",
            "https://api.twitter.com/1.1/guest/activate.json",
            auth=False,
        )
        return data["guest_token"]

    async def _login(self) -> bool:
        update_backup_code = False

        guest_token = await self._request_guest_token()
        self._session.headers["X-Guest-Token"] = guest_token

        flow_token, subtasks = await self._request_login_tasks()
        for _ in range(2):
            flow_token, subtasks = await self._login_enter_user_identifier(flow_token)

        subtask_ids = {subtask.id for subtask in subtasks}
        if "LoginEnterAlternateIdentifierSubtask" in subtask_ids:
            if not self.account.username:
                raise TwitterException("Failed to login: no username to relogin")

        flow_token, subtasks = await self._login_enter_password(flow_token)
        flow_token, subtasks = await self._account_duplication_check(flow_token)

        for subtask in subtasks:
            if subtask.id == "LoginAcid":
                if not self.account.email:
                    raise TwitterException(
                        f"Failed to login. Task id: LoginAcid." f" No email!"
                    )

                if subtask.primary_text == "Check your email":
                    raise TwitterException(
                        f"Failed to login. Task id: LoginAcid."
                        f" Email verification required!"
                        f" No IMAP handler for this version of library :<"
                    )

                try:
                    # fmt: off
                    flow_token, subtasks = await self._login_acid(flow_token, self.account.email)
                    # fmt: on
                except HTTPException as exc:
                    if 399 in exc.api_codes:
                        logger.warning(
                            f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                            f" Bad email!"
                        )
                        raise TwitterException(
                            f"Failed to login. Task id: LoginAcid. Bad email!"
                        )
                    else:
                        raise

        subtask_ids = {subtask.id for subtask in subtasks}

        if "LoginTwoFactorAuthChallenge" in subtask_ids:
            if not self.account.totp_secret:
                raise TwitterException(
                    f"Failed to login. Task id: LoginTwoFactorAuthChallenge. No totp_secret!"
                )

            try:
                # fmt: off
                flow_token, subtasks = await self._login_two_factor_auth_challenge(flow_token, self.account.get_totp_code())
                # fmt: on
            except HTTPException as exc:
                if 399 in exc.api_codes:
                    logger.warning(
                        f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                        f" Bad TOTP secret!"
                    )
                    if not self.account.backup_code:
                        raise TwitterException(
                            f"Failed to login. Task id: LoginTwoFactorAuthChallenge. No backup code!"
                        )

                    # Enter backup code
                    # fmt: off
                    flow_token, subtasks = await self._login_two_factor_auth_choose_method(flow_token)
                    try:
                        flow_token, subtasks = await self._login_two_factor_auth_challenge(flow_token, self.account.backup_code)
                    except HTTPException as exc:
                        if 399 in exc.api_codes:
                            logger.warning(
                                f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                                f" Bad backup code!"
                            )
                            raise TwitterException(
                                f"Failed to login. Task id: LoginTwoFactorAuthChallenge. Bad backup_code!"
                            )
                        else:
                            raise

                    update_backup_code = True
                    # fmt: on
                else:
                    raise

        await self._complete_subtask(flow_token, [])
        return update_backup_code

    async def relogin(self):
        """
        Может вызвать следующую ошибку:
            twitter.errors.BadRequest: (response status: 400)
            (code 398) Can't complete your signup right now.
        Причина возникновения ошибки неизвестна. Не забудьте обработать ее.
        """
        if not self.account.email and not self.account.username:
            raise ValueError("No email or username")

        if not self.account.password:
            raise ValueError("No password")

        update_backup_code = await self._login()
        await self._viewer()

        if update_backup_code:
            await self.update_backup_code()
            logger.warning(
                f"(auth_token={self.account.hidden_auth_token}, id={self.account.id}, username={self.account.username})"
                f" Requested new backup code!"
            )
            # TODO Также обновлять totp_secret

        await self.establish_status()

    async def login(self):
        if self.account.auth_token:
            await self.establish_status()
            if self.account.status not in ("BAD_TOKEN", "CONSENT_LOCKED"):
                return

        await self.relogin()

    async def totp_is_enabled(self):
        if not self.account.id:
            await self.update_account_info()

        url = f"https://twitter.com/i/api/1.1/strato/column/User/{self.account.id}/account-security/twoFactorAuthSettings2"
        response, data = await self.request("GET", url)
        # fmt: off
        return "Totp" in [method_data["twoFactorType"] for method_data in data["methods"]]
        # fmt: on

    async def _request_2fa_tasks(self) -> tuple[str, list[Subtask]]:
        """
        :return: flow_token, tasks
        """
        query = {
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
        return await self._send_raw_subtask(params=query, json=payload)

    async def _two_factor_enrollment_verify_password_subtask(
        self, flow_token: str
    ) -> tuple[str, list[Subtask]]:
        inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentVerifyPasswordSubtask",
                "enter_password": {
                    "link": "next_link",
                    "password": self.account.password,
                },
            }
        ]
        return await self._complete_subtask(flow_token, inputs)

    async def _two_factor_enrollment_authentication_app_begin_subtask(
        self, flow_token: str
    ) -> tuple[str, list[Subtask]]:
        inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppBeginSubtask",
                "action_list": {"link": "next_link"},
            }
        ]
        return await self._complete_subtask(flow_token, inputs)

    async def _two_factor_enrollment_authentication_app_plain_code_subtask(
        self,
        flow_token: str,
    ) -> tuple[str, list[Subtask]]:
        subtask_inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppPlainCodeSubtask",
                "show_code": {"link": "next_link"},
            },
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppEnterCodeSubtask",
                "enter_text": {
                    "link": "next_link",
                    "text": self.account.get_totp_code(),
                },
            },
        ]
        return await self._complete_subtask(flow_token, subtask_inputs)

    async def _finish_2fa_task(self, flow_token: str):
        subtask_inputs = [
            {
                "subtask_id": "TwoFactorEnrollmentAuthenticationAppCompleteSubtask",
                "cta": {"link": "finish_link"},
            }
        ]
        await self._complete_subtask(flow_token, subtask_inputs)

    async def _enable_totp(self):
        # fmt: off
        flow_token, subtasks = await self._request_2fa_tasks()
        flow_token, subtasks = await self._two_factor_enrollment_verify_password_subtask(
            flow_token
        )
        flow_token, subtasks = (await self._two_factor_enrollment_authentication_app_begin_subtask(flow_token))

        for subtask in subtasks:
            if subtask.id == "TwoFactorEnrollmentAuthenticationAppPlainCodeSubtask":
                self.account.totp_secret = subtask.raw_data["show_code"]["code"]
                break

        flow_token, subtasks = await self._two_factor_enrollment_authentication_app_plain_code_subtask(flow_token)

        for subtask in subtasks:
            if subtask.id == "TwoFactorEnrollmentAuthenticationAppCompleteSubtask":
                result = re.search(r"\n[a-z0-9]{12}\n", subtask.raw_data["cta"]["secondary_text"]["text"])
                backup_code = result[0].strip() if result else None
                self.account.backup_code = backup_code
                break

        # fmt: on
        await self._finish_2fa_task(flow_token)

    async def enable_totp(self):
        if await self.totp_is_enabled():
            return

        if not self.account.password:
            raise ValueError("Password required to enable TOTP")

        await self._enable_totp()


class GQLClient:
    _GRAPHQL_URL = "https://twitter.com/i/api/graphql"
    _OPERATION_TO_QUERY_ID = {
        "CreateRetweet": "ojPdsZsimiJrUGLR1sjUtA",
        "FavoriteTweet": "lI07N6Otwv1PhnEgXILM7A",
        "UnfavoriteTweet": "ZYKSe-w7KEslx3JhSIk5LA",
        "CreateTweet": "v0en1yVV-Ybeek8ClmXwYw",
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
    _DEFAULT_VARIABLES = {
        "count": 1000,
        "withSafetyModeUserFields": True,
        "includePromotedContent": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        "withV2Timeline": True,
        "withDownvotePerspective": False,
        "withBirdwatchNotes": True,
        "withCommunity": True,
        "withSuperFollowsUserFields": True,
        "withReactionsMetadata": False,
        "withReactionsPerspective": False,
        "withSuperFollowsTweetFields": True,
        "isMetatagsQuery": False,
        "withReplays": True,
        "withClientEventToken": False,
        "withAttachments": True,
        "withConversationQueryHighlights": True,
        "withMessageQueryHighlights": True,
        "withMessages": True,
    }
    _DEFAULT_FEATURES = {
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "responsive_web_home_pinned_timelines_enabled": True,
        "blue_business_profile_image_shape_enabled": True,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "graphql_timeline_v2_bookmark_timeline": True,
        "hidden_profile_likes_enabled": True,
        "highlights_tweets_tab_ui_enabled": True,
        "interactive_text_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_richtext_consumption_enabled": True,
        "profile_foundations_tweet_stats_enabled": True,
        "profile_foundations_tweet_stats_tweet_frequency": True,
        "responsive_web_birdwatch_note_limit_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_media_download_video_enabled": False,
        "responsive_web_text_conversations_enabled": False,
        "responsive_web_twitter_article_data_v2_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": False,
        "responsive_web_twitter_blue_verified_badge_is_enabled": True,
        "rweb_lists_timeline_redesign_enabled": True,
        "spaces_2022_h2_clipping": True,
        "spaces_2022_h2_spaces_communities": True,
        "standardized_nudges_misinfo": True,
        "subscriptions_verification_info_verified_since_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "tweetypie_unmention_optimization_enabled": True,
        "verified_phone_label_enabled": False,
        "vibe_api_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "hidden_profile_subscriptions_enabled": True,
        "subscriptions_verification_info_is_identity_verified_enabled": True,
    }

    @classmethod
    def _operation_to_url(cls, operation: str) -> tuple[str, str]:
        """
        :return: URL and Query ID
        """
        query_id = cls._OPERATION_TO_QUERY_ID[operation]
        url = f"{cls._GRAPHQL_URL}/{query_id}/{operation}"
        return url, query_id

    def __init__(self, client: Client):
        self._client = client

    async def gql_request(
        self, method, operation, **kwargs
    ) -> tuple[requests.Response, dict]:
        url, query_id = self._operation_to_url(operation)

        if method == "POST":
            payload = kwargs["json"] = kwargs.get("json") or {}
            payload["queryId"] = query_id
        else:
            params = kwargs["params"] = kwargs.get("params") or {}
            ...

        response, data = await self._client.request(method, url, **kwargs)
        return response, data["data"]

    async def user_by_username(self, username: str) -> User | None:
        features = self._DEFAULT_FEATURES
        variables = self._DEFAULT_VARIABLES
        variables["screen_name"] = username
        params = {
            "variables": variables,
            "features": features,
        }
        response, data = await self.gql_request(
            "GET", "UserByScreenName", params=params
        )
        return User.from_raw_data(data["user"]["result"]) if data else None

    async def users_by_ids(
        self, user_ids: Iterable[str | int]
    ) -> dict[int : User | Account]:
        features = self._DEFAULT_FEATURES
        variables = self._DEFAULT_VARIABLES
        variables["userIds"] = list({str(user_id) for user_id in user_ids})
        params = {
            "variables": variables,
            "features": features,
        }
        response, data = await self.gql_request("GET", "UsersByRestIds", params=params)

        users = {}
        for user_data in data["users"]:
            user = User.from_raw_data(user_data["result"])
            users[user.id] = user
            if user.id == self._client.account.id:
                users[self._client.account.id] = self._client.account
        return users
