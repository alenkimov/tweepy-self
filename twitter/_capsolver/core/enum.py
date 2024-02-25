from enum import Enum
from types import DynamicClassAttribute
from typing import List


class MyEnum(Enum):
    @classmethod
    def list(cls) -> List[Enum]:
        return list(map(lambda c: c, cls))

    @classmethod
    def list_values(cls) -> List[str]:
        return list(map(lambda c: c.value, cls))

    @classmethod
    def list_names(cls) -> List[str]:
        return list(map(lambda c: c.name, cls))

    @DynamicClassAttribute
    def name(self) -> str:
        """
        The name of the Enum member
        """
        return self._name_

    @DynamicClassAttribute
    def value(self) -> str:
        """
        The name of the Enum member
        """
        return self._value_


class EndpointPostfixEnm(str, MyEnum):
    """
    Enum stored URL postfixes for API endpoints
    """

    GET_BALANCE = "getBalance"
    CREATE_TASK = "createTask"
    GET_TASK_RESULT = "getTaskResult"
    AKAMAI_BMP_INVOKE = "akamaibmp/invoke"
    AKAMAI_WEB_INVOKE = "akamaiweb/invoke"


class FunCaptchaTypeEnm(str, MyEnum):
    FunCaptchaTask = "FunCaptchaTask"
    FunCaptchaTaskProxyLess = "FunCaptchaTaskProxyLess"


class FunCaptchaClassificationTypeEnm(str, MyEnum):
    FunCaptchaClassification = "FunCaptchaClassification"


class ResponseStatusEnm(str, MyEnum):
    """
    Enum store results `status` field variants

    Notes:
        https://docs.capsolver.com/guide/api-createtask.html
    """

    Idle = "idle"  # Task created
    Processing = "processing"  # Task is not ready yet
    Ready = "ready"  # Task completed, solution object can be found in solution property
    Failed = "failed"  # Task failed, check the errorDescription to know why failed.
