from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, BaseModel, conint

from .enum import ResponseStatusEnm
from .config import APP_ID

"""
HTTP API Request ser
"""


class PostRequestSer(BaseModel):
    clientKey: str = Field(..., description="Client account key, can be found in user account")
    task: dict = Field(None, description="Task object")


class TaskSer(BaseModel):
    type: str = Field(..., description="Task type name", alias="captcha_type")


class RequestCreateTaskSer(PostRequestSer):
    appId: Literal[APP_ID] = APP_ID


class RequestGetTaskResultSer(PostRequestSer):
    taskId: Optional[str] = Field(None, description="ID created by the createTask method")


"""
HTTP API Response ser
"""


class ResponseSer(BaseModel):
    errorId: int = Field(..., description="Error message: `False` - no error, `True` - with error")
    # error info
    errorCode: Optional[str] = Field(None, description="Error code")
    errorDescription: Optional[str] = Field(None, description="Error description")


class CaptchaResponseSer(ResponseSer):
    taskId: Optional[str] = Field(None, description="Task ID for future use in getTaskResult method.")
    status: ResponseStatusEnm = Field(ResponseStatusEnm.Processing, description="Task current status")
    solution: Dict[str, Any] = Field(None, description="Task result data. Different for each type of task.")

    class Config:
        populate_by_name = True


class ControlResponseSer(ResponseSer):
    balance: Optional[float] = Field(0, description="Account balance value in USD")


"""
Other ser
"""


class CaptchaOptionsSer(BaseModel):
    api_key: str
    sleep_time: conint(ge=5) = 5


"""
Captcha tasks ser
"""


class FunCaptchaClassificationOptionsSer(TaskSer):
    images: List[str] = Field(..., description="Base64-encoded images, do not include 'data:image/***;base64,'")
    question: str = Field(
        ...,
        description="Question name. this param value from API response game_variant field. Exmaple: maze,maze2,flockCompass,3d_rollball_animals",
    )


class FunCaptchaSer(TaskSer):
    websiteURL: str = Field(..., description="Address of a webpage with Funcaptcha")
    websitePublicKey: str = Field(..., description="Funcaptcha website key.")
    funcaptchaApiJSSubdomain: Optional[str] = Field(
        None,
        description="A special subdomain of funcaptcha.com, from which the JS captcha widget should be loaded."
        "Most FunCaptcha installations work from shared domains.",
    )
