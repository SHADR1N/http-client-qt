from dataclasses import dataclass, field, fields
from enum import IntEnum, Enum

try:
    from PyQt5.QtCore import QByteArray
except ImportError:
    from PySide6.QtCore import QByteArray


class ResultType(IntEnum):
    error = 0
    success = 1
    abort = 2
    timeout = 3
    invalid_request = 4


class ErrorCode(Enum):
    timeout = "TIMEOUT_REQUEST"
    abort = "ABORTED_REQUEST"
    unprocessable_entities = "UNPROCESSABLE_ENTITIES"
    invalid_request = "INVALID_REQUEST"


@dataclass
class HttpClientResult:
    type: ResultType
    status_code: int = field(default_factory=int)
    text: str = field(default_factory=str)
    json: dict = field(default_factory=dict)
    bytes: QByteArray = field(default_factory=QByteArray)
