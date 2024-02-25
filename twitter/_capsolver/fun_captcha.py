from typing import List, Union

from .core.base import BaseCaptcha
from .core.enum import FunCaptchaTypeEnm, FunCaptchaClassificationTypeEnm
from .core.serializer import (
    FunCaptchaSer,
    CaptchaResponseSer,
    FunCaptchaClassificationOptionsSer,
)


class FunCaptcha(BaseCaptcha):
    """
    The class is used to work with Capsolver FuncaptchaTask methods.

    Args:
        api_key: Capsolver API key
        captcha_type: Captcha type name, like ``FunCaptchaTaskProxyLess`` and etc.
        websiteURL: Address of a webpage with Geetest.
        websitePublicKey: Funcaptcha website key.

    Examples:
        >>> with FunCaptcha(api_key="CAI-1324...",
        ...             captcha_type="FunCaptchaTaskProxyLess",
        ...             websiteURL="https://api.funcaptcha.com/fc/api/nojs/",
        ...             websitePublicKey="69A21A01-CC7B-B9C6-0F9A-E7FA06677FFC",
        ...             funcaptchaApiJSSubdomain="https://api.funcaptcha.com/"
        ...         ) as instance:
        >>>     instance.captcha_handler()
        CaptchaResponseSer(errorId=0,
                           errorCode=None,
                           errorDescription=None,
                           taskId='73bdcd28-6c77-4414-8....',
                           status=<ResponseStatusEnm.Ready: 'ready'>,
                           solution={'token': '44795sds...'}
                          )

        >>> with FunCaptcha(api_key="CAI-1324...",
        ...             captcha_type="FunCaptchaTaskProxyLess",
        ...             websiteURL="https://api.funcaptcha.com/fc/api/nojs/",
        ...             websitePublicKey="69A21A01-CC7B-B9C6-0F9A-E7FA06677FFC",
        ...             funcaptchaApiJSSubdomain="https://api.funcaptcha.com/"
        ...         ) as instance:
        >>>     await instance.aio_captcha_handler()
        CaptchaResponseSer(errorId=0,
                           errorCode=None,
                           errorDescription=None,
                           taskId='73bdcd28-6c77-4414-8....',
                           status=<ResponseStatusEnm.Ready: 'ready'>,
                           solution={'token': '44795sds...'}
                          )

    Returns:
        CaptchaResponseSer model with full server response

    Notes:
        https://docs.capsolver.com/guide/captcha/FunCaptcha.html
    """

    def __init__(
        self,
        captcha_type: Union[FunCaptchaTypeEnm, str],
        websiteURL: str,
        websitePublicKey: str,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if captcha_type in FunCaptchaTypeEnm.list():
            self.task_params = FunCaptchaSer(**locals()).dict()
        else:
            raise ValueError(
                f"""Invalid `captcha_type` parameter set for `{self.__class__.__name__}`,
                available - {FunCaptchaTypeEnm.list()}"""
            )
        for key in kwargs:
            self.task_params.update({key: kwargs[key]})

    def captcha_handler(self) -> CaptchaResponseSer:
        """
        Sync solving method

        Examples:
            >>> FunCaptcha(api_key="CAI-BA9XXXXXXXXXXXXX2702E010",
            ...         captcha_type="FunCaptchaTaskProxyLess",
            ...         websiteURL="https://api.funcaptcha.com/fc/api/nojs/",
            ...         websitePublicKey="69A21A01-CC7B-B9C6-0F9A-E7FA06677FFC",
            ...         funcaptchaApiJSSubdomain="https://api.funcaptcha.com/"
            ...        ).captcha_handler()
            CaptchaResponseSer(errorId=0,
                               errorCode=None,
                               errorDescription=None,
                               taskId='73bdcd28-6c77-4414-8....',
                               status=<ResponseStatusEnm.Ready: 'ready'>,
                               solution={'token': '44795sds...'}
                              )

            >>> FunCaptcha(api_key="CAI-BA9XXXXXXXXXXXXX2702E010",
            ...         captcha_type="FuncaptchaTask",
            ...         websiteURL="https://api.funcaptcha.com/fc/api/nojs/",
            ...         websitePublicKey="69A21A01-CC7B-B9C6-0F9A-E7FA06677FFC",
            ...         funcaptchaApiJSSubdomain="https://api.funcaptcha.com/",
            ...         proxyType="http",
            ...         proxyAddress="0.0.0.0",
            ...         proxyPort=9090,
            ...        ).captcha_handler()
            CaptchaResponseSer(errorId=0,
                               errorCode=None,
                               errorDescription=None,
                               taskId='73bdcd28-6c77-4414-8....',
                               status=<ResponseStatusEnm.Ready: 'ready'>,
                               solution={'token': '44795sds...'}
                              )

        Returns:
            CaptchaResponseSer model with full service response

        Notes:
            Check class docstring for more info
        """
        return self._processing_captcha(create_params=self.task_params)

    async def aio_captcha_handler(self) -> CaptchaResponseSer:
        """
        Async method for captcha solving

        Examples:
            >>> await FunCaptcha(api_key="CAI-1324...",
            ...         captcha_type="FunCaptchaTaskProxyLess",
            ...         websiteURL="https://api.funcaptcha.com/fc/api/nojs/",
            ...         websitePublicKey="69A21A01-CC7B-B9C6-0F9A-E7FA06677FFC",
            ...         funcaptchaApiJSSubdomain="https://api.funcaptcha.com/"
            ...        ).aio_captcha_handler()
            CaptchaResponseSer(errorId=0,
                               errorCode=None,
                               errorDescription=None,
                               taskId='73bdcd28-6c77-4414-8....',
                               status=<ResponseStatusEnm.Ready: 'ready'>,
                               solution={'token': '44795sds...'}
                              )

            >>> await FunCaptcha(api_key="CAI-1324...",
            ...         captcha_type="FuncaptchaTask",
            ...         websiteURL="https://api.funcaptcha.com/fc/api/nojs/",
            ...         websitePublicKey="69A21A01-CC7B-B9C6-0F9A-E7FA06677FFC",
            ...         funcaptchaApiJSSubdomain="https://api.funcaptcha.com/",
            ...         proxyType="http",
            ...         proxyAddress="0.0.0.0",
            ...         proxyPort=9090,
            ...        ).aio_captcha_handler()
            CaptchaResponseSer(errorId=0,
                               errorCode=None,
                               errorDescription=None,
                               taskId='73bdcd28-6c77-4414-8....',
                               status=<ResponseStatusEnm.Ready: 'ready'>,
                               solution={'token': '44795sds...'}
                              )

            >>> with open('some_image.jpeg', 'rb') as img_file:
            ...    img_data = img_file.read()
            >>> body = base64.b64encode(img_data).decode("utf-8")
            >>> await FunCaptcha(api_key="CAI-1324...",
            ...         captcha_type="FunCaptchaClassification"
            ...        ).aio_captcha_handler(
            ...                     image=body,
            ...                     question="Ask your question")
            CaptchaResponseSer(errorId=0,
                               errorCode=None,
                               errorDescription=None,
                               taskId='73bdcd28-6c77-4414-8....',
                               status=<ResponseStatusEnm.Ready: 'ready'>,
                               solution={'token': '44795sds...'}
                              )

        Returns:
            CaptchaResponseSer model with full service response

        Notes:
            Check class docstring for more info
        """
        return await self._aio_processing_captcha(create_params=self.task_params)


class FunCaptchaClassification(BaseCaptcha):
    """
    The class is used to work with Capsolver FunCaptchaClassification methods.

    Args:
        api_key: Capsolver API key
        captcha_type: Captcha type name, like ``FunCaptchaClassification`` and etc.
        images: Base64 encoded image, can be a screenshot (pass only the hexagonal image, do not pass the rest of the content)
        question: Question name. this param value from API response game_variant field. Exmaple: maze,maze2,flockCompass,3d_rollball_animals

    Examples:
        >>> FunCaptchaClassification(api_key="CAI-1324...",
        ...             captcha_type="FunCaptchaClassification",
        ...             images=["image payload"],
        ...             question="maze2",
        ...         ).captcha_handler()
        CaptchaResponseSer(errorId=0,
                           errorCode=None,
                           errorDescription=None,
                           taskId='73bdcd28-6c77-4414-8....',
                           status=<ResponseStatusEnm.Ready: 'ready'>,
                           solution={"objects": [ 4 ]}
                          )

    Returns:
        CaptchaResponseSer model with full server response

    Notes:
        https://docs.capsolver.com/guide/recognition/FunCaptchaClassification.html
    """

    def __init__(
        self,
        images: List[str],
        question: str,
        captcha_type: Union[
            FunCaptchaClassificationTypeEnm, str
        ] = FunCaptchaClassificationTypeEnm.FunCaptchaClassification,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if captcha_type in FunCaptchaClassificationTypeEnm.list():
            self.task_params = FunCaptchaClassificationOptionsSer(**locals()).dict()
        else:
            raise ValueError(
                f"""Invalid `captcha_type` parameter set for `{self.__class__.__name__}`,
                available - {FunCaptchaClassificationTypeEnm.list()}"""
            )
        for key in kwargs:
            self.task_params.update({key: kwargs[key]})

    def captcha_handler(self) -> CaptchaResponseSer:
        """
        Sync solving method

        Returns:
            CaptchaResponseSer model with full service response

        Notes:
            Check class docstring for more info
        """
        return self._processing_captcha(create_params=self.task_params)

    async def aio_captcha_handler(self) -> CaptchaResponseSer:
        """
        Async method for captcha solving

        Returns:
            CaptchaResponseSer model with full service response

        Notes:
            Check class docstring for more info
        """
        return await self._aio_processing_captcha(create_params=self.task_params)
