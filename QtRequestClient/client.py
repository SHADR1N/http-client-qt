import json
import base64
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from datetime import datetime

from QtRequestClient.entity import HttpClientResult, ResultType

try:
    from PyQt5.QtCore import (QObject, QUrl, QTimer, QUrlQuery, pyqtSignal as Signal)
    from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkReply, QNetworkRequest)
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from PySide6.QtCore import (QObject, QUrl, QTimer, QUrlQuery, Signal)
    from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkReply, QNetworkRequest)


class QtHttpClient(QObject):
    """
    HTTP client supporting retries, timeouts, progress and optional callbacks.
    Always emits `requestCompleted` signal and also calls `callback` if provided.
    """
    requestCompleted = Signal(object)       # HttpClientResult
    downloadProgress = Signal(int, int)     # bytesReceived, bytesTotal

    def __init__(self, parent=None, retry_errors: list = None):
        super().__init__(parent)
        self.network_manager = QNetworkAccessManager(self)
        self.retry_errors = retry_errors

    def get(self, url: str, params: dict = None, retries: int = 1,
            timeout: int = None, callback: callable = None):
        self._make_request('GET', url, params, retries, timeout, callback)

    def post(self, url: str, data: dict = None, retries: int = 1,
             timeout: int = None, callback: callable = None):
        self._make_request('POST', url, data, retries, timeout, callback)

    def put(self, url: str, data: dict = None, retries: int = 1,
            timeout: int = None, callback: callable = None):
        self._make_request('PUT', url, data, retries, timeout, callback)

    def delete(self, url: str, retries: int = 1,
               timeout: int = None, callback: callable = None):
        self._make_request('DELETE', url, None, retries, timeout, callback)

    def _make_request(self, method: str, url: str, payload: dict,
                      retries: int, timeout: int, callback: callable):
        # Save context
        self._method = method
        self._url = url
        self._payload = payload
        self._initial_retries = retries
        self._remaining_retries = retries
        self._history = []
        self._timeout = timeout
        self._callback = callback
        self.total_size = 0

        # Prepare URL and data
        qurl = QUrl(url)
        data = None
        if method == 'GET' and payload:
            query = QUrlQuery()
            for k, v in payload.items():
                query.addQueryItem(str(k), str(v))
            qurl.setQuery(query)
        elif payload:
            data = json.dumps(payload).encode('utf-8')

        request = QNetworkRequest(qurl)
        request.setRawHeader(b'User-Agent', b'MyApp/1.0')
        request.setRawHeader(b'Accept', b'application/json')

        # Send request
        if method == 'GET':
            reply = self.network_manager.get(request)
        elif method == 'POST':
            reply = self.network_manager.post(request, data)
        elif method == 'PUT':
            reply = self.network_manager.put(request, data)
        elif method == 'DELETE':
            reply = self.network_manager.deleteResource(request)
        else:
            raise ValueError(f'Method {method} not supported')

        # Timeout timer
        if timeout:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(reply.abort)
            timer.start(timeout * 1000)

        # Progress
        reply.downloadProgress.connect(
            lambda rec, tot: self.downloadProgress.emit(rec, reply.header(QNetworkRequest.ContentLengthHeader) or 0)
        )
        # Error and finished
        reply.error.connect(lambda code: self._handle_error(reply, code))
        reply.finished.connect(lambda: self._handle_finished(reply))

    def _handle_error(self, reply, error_code):
        # Record history
        err = reply.errorString()
        self._history.append({'error': err, 'time': datetime.now().isoformat()})
        self._remaining_retries -= 1
        should_retry = self.retry_errors is None or error_code in self.retry_errors
        if should_retry and self._remaining_retries > 0:
            # Retry
            self._make_request(self._method, self._url, self._payload,
                               self._remaining_retries, self._timeout, self._callback)
            return

        # Final error result
        result = HttpClientResult(
            url=self._url,
            status_code=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0,
            type=ResultType.error,
            text=err,
            raw=b'',
            attempts=self._initial_retries - self._remaining_retries,
            history=self._history.copy()
        )
        # Always emit signal
        self.requestCompleted.emit(result)
        # Also call callback if exists
        if callable(self._callback):
            self._callback(result)

    def _handle_finished(self, reply):
        if reply.error() != QNetworkReply.NoError:
            return
        raw = reply.readAll().data()
        try:
            text = raw.decode('utf-8')
            json_data = json.loads(text)
        except Exception:
            text = raw.decode('utf-8', errors='ignore')
            json_data = {}
        result = HttpClientResult(
            url=reply.url().toString(),
            status_code=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute),
            type=ResultType.success,
            text=text,
            json=json_data,
            raw=raw,
            attempts=self._initial_retries - self._remaining_retries + 1,
            history=self._history.copy()
        )
        # Always emit signal
        self.requestCompleted.emit(result)
        # Also call callback if exists
        if callable(self._callback):
            self._callback(result)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return True