import sys
import functools
import json

from typing import Any, Union

try:
    from PyQt5.QtCore import QUrl, QObject, QTimer
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
except ImportError:
    from PySide6.QtCore import QUrl, QObject, QTimer, Signal
    from PySide6.QtNetwork import QNetworkRequest, QNetworkReply, QNetworkAccessManager


class QtHttpClient(QObject):
    error_code = {
        "Connection refused": "SERVER_OFFLINE",
        "Operation canceled": "TIMEOUT_REQUEST",
        "Unprocessable Entity": "ERROR_ARGS",
        "INVALID_REQUEST": "INVALID_REQUEST"
    }

    cancel = Signal(object)
    downloading_progress = Signal(int)

    def __init__(self, access_token="", lang="en", parent=None):
        super().__init__(parent=parent)
        self.responses = []
        self.lang = lang
        self.access_token = access_token
        self.network_manager = QNetworkAccessManager()
        self.total_size = 0

    def get(
            self,
            url,
            timeout: int = 3,
            send_result: Any = None,
            headers: dict = None
    ):
        self.send_request(method="GET", url=url, timeout=timeout, send_result=send_result, headers=headers)

    def post(
            self,
            url,
            timeout: int = 3,
            data: Union[str, dict, list] = None,
            send_result: Any = None,
            headers: dict = None
    ):
        self.send_request(method="POST", url=url, timeout=timeout, parameters=data, send_result=send_result, headers=headers)

    def put(
            self,
            url,
            timeout: int = 3,
            data: Union[str, dict, list] = None,
            send_result: Any = None,
            headers: dict = None
    ):
        self.send_request(method="PUT", url=url, timeout=timeout, parameters=data, send_result=send_result, headers=headers)

    def delete(
            self,
            url,
            timeout: int = 3,
            data: Union[str, dict, list] = None,
            send_result: str = None,
            headers: dict = None
    ):
        self.send_request(method="DELETE", url=url, timeout=timeout, parameters=data, send_result=send_result, headers=headers)

    def send_request(
            self,
            method,
            url: str,
            parameters: Union[str, dict, list] = None,
            timeout: int = None,
            send_result: Any = None,
            headers: dict = None
    ):
        if not headers:
            headers = {}

        url = QUrl(url)
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        if self.access_token:
            authorization_header = "Bearer " + self.access_token
            request.setRawHeader(b"Authorization", authorization_header.encode())

        request.setRawHeader(b"User-Agent", b"Application")

        if self.lang:
            request.setRawHeader(b"Accept-language", self.lang.encode())

        for key, param in headers.items():
            request.setRawHeader(key.encode(), param.encode())

        if parameters:
            data = bytes(str(json.dumps(parameters)), encoding="utf-8")
        else:
            data = None

        self.make_request(method, request, send_result=send_result, timeout=timeout, data=data)

    def make_request(self, method, request, send_result=None, timeout=None, data=None, progress=False):
        if method == "GET" or method == "HEAD":
            reply = self.network_manager.get(request)
        elif method == "POST":
            reply = self.network_manager.post(request, data)
        elif method == "PUT":
            reply = self.network_manager.put(request, data)
        elif method == "DELETE":
            reply = self.network_manager.deleteResource(request)
        else:
            return

        if timeout:
            # Set a timeout for the request (e.g., 5 seconds)
            timeout = timeout * 1000
            timer = QTimer(self)
            timer.timeout.connect(functools.partial(self.handle_timeout, reply, timer))
            timer.start(timeout)

        # Connect the finished signal to the function handling the response
        reply.finished.connect(functools.partial(self.handle_response, reply, send_result))
        if progress is True:
            reply.metaDataChanged.connect(functools.partial(self.update_total_size, reply))
            reply.downloadProgress.connect(self.handle_progress)

    def update_total_size(self, reply):
        self.total_size = int(reply.header(QNetworkRequest.ContentLengthHeader))

    def handle_progress(self, bytes_received, bytes_total):
        bytes_total = self.total_size

        if bytes_total <= 0:
            bytes_total = 1
        if bytes_received <= 0:
            bytes_received = 1

        percent = int((bytes_received / bytes_total) * 100)
        self.downloading_progress.emit(percent)

    def handle_timeout(self, reply, timer):
        reply.abort()
        timer.stop()
        timer.deleteLater()

    def handle_response(self, reply: QNetworkReply, send_result=None):
        status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)

        if reply.error() in (QNetworkReply.NetworkError.NoError,):
            if status_code in (301, 302):
                # Получаем новый URL из заголовка "Location"
                redirect_url: QNetworkRequest.Attribute = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)

                if redirect_url.isValid():
                    # Повторяем запрос с новым URL
                    self.make_request("GET", QNetworkRequest(redirect_url), send_result=send_result, progress=True)
                    return

            all_data = reply.readAll()
            data = all_data.data()

            # Попытка декодировать данные как UTF-8
            try:
                decoded_data = data.decode("utf-8")
                # Попытка сериализовать данные как JSON
                try:
                    json_data = json.loads(decoded_data)
                    result = json_data  # Данные можно сериализовать в JSON
                except json.JSONDecodeError:
                    result = decoded_data  # Данные текстовые, но не JSON
                    if not result:
                        raise ZeroDivisionError
            except (UnicodeDecodeError, ZeroDivisionError):
                result = all_data

            # Передача результата
            self.cancel.emit(result)
            if send_result:
                send_result(result)

        else:

            string = reply.errorString()
            if status_code == 422:
                string = "Unprocessable Entity"

            if status_code == 500:
                string = "INVALID_REQUEST"

            self.error_code[string] if string in self.error_code else print(status_code, string)
            result = {"error": self.error_code[string] if string in self.error_code else "NOT_FOUND_ERROR"}
            self.cancel.emit(result)
            if send_result:
                send_result(result)
