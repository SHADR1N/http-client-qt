import json
from datetime import datetime

from .entity import HttpClientResult, ResultType

try:
    from PyQt5.QtCore import (QObject, QUrl, QTimer, QUrlQuery, pyqtSignal as Signal)
    from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkReply, QNetworkRequest)
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from PySide6.QtCore import (QObject, QUrl, QTimer, QUrlQuery, Signal)
    from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkReply, QNetworkRequest)
    from PySide6.QtWidgets import QApplication


class QtHttpClient(QObject):
    responseReady = Signal(object)       # Emitted on successful response
    allRetriesFailed = Signal(object)    # Emitted after all retries fail
    downloadProgress = Signal(int, int)  # bytesReceived, bytesTotal
    requestCompleted = Signal(object)    # Emitted on any result

    def __init__(self, parent=None, retry_errors: list = None):
        super().__init__(parent)
        self.network_manager = QNetworkAccessManager(self)
        self.retry_errors = retry_errors

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return True

    def get(self, url: str, params: dict = None, retries: int = 1, timeout: int = None):
        self._make_request('GET', url, params, retries, timeout)

    def post(self, url: str, data: dict = None, retries: int = 1, timeout: int = None):
        self._make_request('POST', url, data, retries, timeout)

    def put(self, url: str, data: dict = None, retries: int = 1, timeout: int = None):
        self._make_request('PUT', url, data, retries, timeout)

    def delete(self, url: str, retries: int = 1, timeout: int = None):
        self._make_request('DELETE', url, None, retries, timeout)

    def _make_request(self, method: str, url: str, payload: dict, retries: int, timeout: int):
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

        # initialize attempt tracking and history
        self._initial_retries = retries
        self._remaining_retries = retries
        self._history = []

        def do_request():
            # perform operation
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

            # timeout handling
            if timeout:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(reply.abort)
                timer.start(timeout * 1000)

            # connect signals with bound context
            reply.downloadProgress.connect(self.downloadProgress.emit)
            reply.error.connect(lambda code: self._handle_error(reply, method, url, payload, timeout, code))
            reply.finished.connect(lambda: self._handle_finished(reply, method, url, payload, timeout))

        do_request()

    def _handle_error(self, reply, method, url, payload, timeout, error_code):
        # record error event
        err_str = reply.errorString()
        self._history.append({'error': err_str, 'time': datetime.now().isoformat()})
        # decrement
        self._remaining_retries -= 1
        should_retry = self.retry_errors is None or error_code in self.retry_errors
        if should_retry and self._remaining_retries > 0:
            # retry same request
            self._make_request(method, url, payload, self._remaining_retries, timeout)
        else:
            # all retries exhausted: emit error
            result = HttpClientResult(
                url=url,
                status_code=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0,
                type=ResultType.error,
                text=err_str,
                raw=b'',
                attempts=self._initial_retries - self._remaining_retries,
                history=self._history.copy()
            )
            self.allRetriesFailed.emit(result)
            self.requestCompleted.emit(result)

    def _handle_finished(self, reply, method, url, payload, timeout):
        # ignore if error (handled already)
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
            url=url,
            status_code=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute),
            type=ResultType.success,
            text=text,
            json=json_data,
            raw=raw,
            attempts=self._initial_retries - self._remaining_retries + 1,
            history=self._history.copy()
        )
        self.responseReady.emit(result)
        self.requestCompleted.emit(result)
