import json
from dataclasses import dataclass, field, fields, asdict
from enum import IntEnum, Enum

try:
    from PyQt5.QtCore import QByteArray
except ImportError:
    from PySide6.QtCore import QByteArray


class ResultType(IntEnum):
    error = 0
    success = 1
    timeout = 3

@dataclass
class HttpClientResult:
    url: str
    status_code: int
    type: ResultType
    text: str = ''
    json: dict = field(default_factory=dict)
    raw: bytes = field(default_factory=bytes)
    attempts: int = 0
    history: list = field(default_factory=list)  # each entry: {'error': str, 'time': str}

    def __repr__(self):
        data = asdict(self)
        data['type'] = self.type.name
        raw_bytes = data.get('raw', b'')
        if isinstance(raw_bytes, (bytes, bytearray)):
            data['raw'] = f"<{len(raw_bytes)} bytes>"
        return json.dumps(data, indent=4, ensure_ascii=False)

