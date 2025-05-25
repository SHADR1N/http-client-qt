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
        self._error_handled_for_reply = False
        self.current_reply = None
        self.request_timeout_timer = None

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
        self._error_handled_for_reply = False

        # Clean up previous reply if any
        if self.current_reply:
            try:
                self.current_reply.error.disconnect()
            except TypeError: pass # Already disconnected or no connection
            try:
                self.current_reply.finished.disconnect()
            except TypeError: pass
            try:
                self.current_reply.downloadProgress.disconnect()
            except TypeError: pass
            self.current_reply.deleteLater()
            self.current_reply = None

        # Clean up previous timer if any
        if self.request_timeout_timer:
            self.request_timeout_timer.stop()
            self.request_timeout_timer.deleteLater()
            self.request_timeout_timer = None

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
        
        self.current_reply = reply

        # Timeout timer
        if timeout:
            self.request_timeout_timer = QTimer(self)
            self.request_timeout_timer.setSingleShot(True)
            # Connect to self.current_reply.abort for clarity, though reply.abort would also work
            self.request_timeout_timer.timeout.connect(self.current_reply.abort)
            self.request_timeout_timer.start(timeout * 1000)
        else:
            self.request_timeout_timer = None # Ensure it's None if no timeout

        # Progress
        self.current_reply.downloadProgress.connect(
            lambda rec, tot: self.downloadProgress.emit(rec, self.current_reply.header(QNetworkRequest.ContentLengthHeader) or 0)
        )
        # Error and finished
        # Pass self.current_reply to handlers to ensure they operate on the correct instance
        self.current_reply.error.connect(lambda code: self._handle_error(self.current_reply, code))
        self.current_reply.finished.connect(lambda: self._handle_finished(self.current_reply))

    def _handle_error(self, reply, error_code):
        # Record history
        err = reply.errorString()
        self._history.append({'error': err, 'time': datetime.now().isoformat()})
        self._remaining_retries -= 1
        should_retry = self.retry_errors is None or error_code in self.retry_errors
        
        # Ensure the reply parameter is the one we are tracking if it's self.current_reply
        # This helps if _handle_error is called from _handle_finished with a different reply instance
        # However, the signal connections now ensure 'reply' is self.current_reply.

        if should_retry and self._remaining_retries > 0:
            reply.abort() # Abort before deleting
            # Disconnect signals before deleting
            try: reply.error.disconnect()
            except TypeError: pass
            try: reply.finished.disconnect()
            except TypeError: pass
            try: reply.downloadProgress.disconnect()
            except TypeError: pass
            reply.deleteLater()
            # _make_request will handle stopping/deleting the old timer
            # and cleaning self.current_reply before assigning a new one.
            self._make_request(self._method, self._url, self._payload,
                               self._remaining_retries, self._timeout, self._callback)
            return

        # Final error result
        self._error_handled_for_reply = True
        result = HttpClientResult(
            url=self._url,
            status_code=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0,
            type=ResultType.error,
            text=err,
            raw=b'',
            attempts=self._initial_retries - self._remaining_retries,
            history=self._history.copy()
        )
        self._finalize_request(result) # Timer is stopped/deleted here
        reply.deleteLater() # Delete reply after finalizing

    def _handle_finished(self, reply):
        # Ensure the reply parameter is self.current_reply for consistency
        # This should be true due to how signals are connected in _make_request

        if reply.error() != QNetworkReply.NoError:
            if self._error_handled_for_reply:
                reply.deleteLater() # Clean up the reply if error already handled
                return
            else:
                # Error occurred, but not yet handled by _handle_error.
                # Route through _handle_error for consistent processing and retries.
                # _handle_error will manage reply.deleteLater()
                self._handle_error(reply, reply.error())
                return
        
        raw = reply.readAll().data() # Read data before reply might be deleted in some path
        try:
            text = raw.decode('utf-8')
            json_data = json.loads(text)
        except Exception as e:
            self._history.append({'error': f'JSON decoding failed: {str(e)}', 'time': datetime.now().isoformat()})
            status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            is_success_status = 200 <= status_code < 300

            if is_success_status:
                self._remaining_retries -= 1
                if self._remaining_retries > 0:
                    reply.abort()
                    # Disconnect signals before deleting
                    try: reply.error.disconnect()
                    except TypeError: pass
                    try: reply.finished.disconnect()
                    except TypeError: pass
                    try: reply.downloadProgress.disconnect()
                    except TypeError: pass
                    reply.deleteLater()
                    # _make_request will handle stopping/deleting the old timer
                    # and cleaning self.current_reply before assigning a new one.
                    self._make_request(self._method, self._url, self._payload,
                                       self._remaining_retries, self._timeout, self._callback)
                    return

            # Final failure for JSON decoding (non-2xx or out of retries)
            self._error_handled_for_reply = True # Mark error as handled for this reply
            error_text = f"Failed to decode JSON response. Original error: {str(e)}"
            result = HttpClientResult(
                url=reply.url().toString(),
                status_code=status_code,
                type=ResultType.error,
                text=error_text,
                raw=raw,
                attempts=self._initial_retries - self._remaining_retries,
                history=self._history.copy()
            )
        self._finalize_request(result) # Timer is stopped/deleted here
        reply.deleteLater() # Delete reply after finalizing
            return

        # Successful JSON decoding or not a JSON response
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
        self._finalize_request(result) # Timer is stopped/deleted here
        reply.deleteLater() # Delete reply after finalizing

    def _finalize_request(self, result: HttpClientResult):
        # Stop and clean up the timer associated with the request
        if self.request_timeout_timer:
            self.request_timeout_timer.stop()
            self.request_timeout_timer.deleteLater()
            self.request_timeout_timer = None

        # Always emit signal
        self.requestCompleted.emit(result)
        # Also call callback if exists
        if callable(self._callback):
            self._callback(result)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return True