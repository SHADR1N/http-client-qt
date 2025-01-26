import json

from QtRequestClient.entity import ErrorCode, HttpClientResult, ResultType

try:
    from PyQt5.QtCore import QUrl, QObject, QTimer, QUrlQuery
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
except ImportError:
    from PySide6.QtCore import QUrl, QObject, QTimer, Signal, QUrlQuery
    from PySide6.QtNetwork import QNetworkRequest, QNetworkReply, QNetworkAccessManager


class Utilities:
    def update_total_size(self, reply):
        if reply.header(QNetworkRequest.ContentLengthHeader):
            self.total_size = int(reply.header(QNetworkRequest.ContentLengthHeader))

    def handle_progress(self, bytes_received, bytes_total):
        bytes_total = self.total_size

        if bytes_total <= 0:
            bytes_total = 1
        if bytes_received <= 0:
            bytes_received = 1

        percent = int((bytes_received / bytes_total) * 100)
        self.download_progress.emit(percent)

    def unparse_result(self, reply: QNetworkReply):
        all_data = reply.readAll()
        data = all_data.data()

        # Попытка декодировать данные как UTF-8
        try:
            decoded_data = data.decode("utf-8")
            # Попытка сериализовать данные как JSON
            try:
                json_data = json.loads(decoded_data)
                result = HttpClientResult(
                    url=reply.url().toString(),
                    type=ResultType.success,
                    status_code=200,
                    json=json_data
                )
            except json.JSONDecodeError:
                result = HttpClientResult(
                    url=reply.url().toString(),
                    type=ResultType.success,
                    status_code=200,
                    text=decoded_data
                )
                if not result:
                    raise ZeroDivisionError
        except (UnicodeDecodeError, ZeroDivisionError):
            result = HttpClientResult(
                url=reply.url().toString(),
                type=ResultType.success,
                status_code=200,
                bytes=all_data
            )
        return result


class Handlers(QObject, Utilities):
    exception = Signal(object)
    download_progress = Signal(int)
    upload_progress = Signal(int)
    result = Signal(object)

    def __init__(self, parent=None, ignore_redirect=None):
        super().__init__(parent=parent)
        self.ignore_redirect = ignore_redirect if ignore_redirect is not None else []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.exception.emit(exc_val)
        return True

    def handle_error(self, reply: QNetworkReply, method, request, request_retries, send_result, timeout, data, progress, error=None):
        if request_retries is None: request_retries = 0
        request_retries -= 1

        if request_retries > 0:
            self.current_request.update({"request_retries": request_retries})
            self.request(**self.current_request)
        else:
            error_message = reply.errorString()
            self.retry_failed.emit(error_message)

    def handle_allowed_redirect(self, reply: QNetworkReply, send_result: callable):
        # Получаем новый URL из заголовка "Location"
        progress = True
        redirect_url: QNetworkRequest.Attribute = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)

        if redirect_url.isValid():
            if [i for i in self.ignore_redirect if i in reply.url().toString()]:
                progress = False
            self.make_request("GET", QNetworkRequest(redirect_url), request_retries=self.current_request["request_retries"], progress=progress, send_result=send_result)

    def handle_response(self, reply: QNetworkReply, send_result=None):
        status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if status_code == 422:
            string_code = ErrorCode.unprocessable_entities
        elif status_code == 500:
            string_code = ErrorCode.invalid_request
        else:
            string_code = None

        if reply.error() in (QNetworkReply.NetworkError.NoError,):
            if status_code in (301, 302):
                return self.handle_allowed_redirect(reply, send_result)

            result = self.unparse_result(reply)
            self.result.emit(result)

        else:
            result = HttpClientResult(
                url=reply.url().toString(),
                type=ResultType.error,
                status_code=status_code,
                text=string_code or reply.errorString()
            )
            self.result.emit(result)

        if send_result:
            send_result(result)

