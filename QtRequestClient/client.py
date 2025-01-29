import functools
import functools
import json
from typing import Any, Union, Optional

from QtRequestClient.handlers import Handlers
from QtRequestClient.logger import logger

try:
    from PyQt5.QtCore import QUrl, QObject, QTimer, QUrlQuery
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QUrl, QObject, QTimer, Signal, QUrlQuery
    from PySide6.QtNetwork import QNetworkRequest, QNetworkReply, QNetworkAccessManager


class QtHttpClient(Handlers):
    error_code = {
        "Connection refused": "SERVER_OFFLINE",
        "Operation canceled": "TIMEOUT_REQUEST",
        "Unprocessable Entity": "ERROR_ARGS",
        "INVALID_REQUEST": "INVALID_REQUEST"
    }

    cancel = Signal(object)
    retry_failed = Signal(object)
    download_progress = Signal(int)

    def __init__(self, parent=None, ignore_redirect=None):
        super().__init__(parent=parent, ignore_redirect=ignore_redirect)
        self.current_request = {}
        self.network_manager = QNetworkAccessManager()
        self.total_size = 0

    def get(self, url: str, data: Union[str, dict, list] = None, send_result: Optional[callable] = None, **kwargs):
        logger.debug(f"New request GET with url={url}")
        self.request(method="GET", url=url, parameters=data, send_result=send_result, **kwargs)

    def post(self, url: str, data: Union[str, dict, list] = None, send_result: Optional[callable] = None, **kwargs):
        logger.debug(f"New request POST with url={url}")
        self.request(method="POST", url=url, parameters=data, send_result=send_result, **kwargs)

    def put(self, url: str, data: Union[str, dict, list] = None, send_result: Optional[callable] = None, **kwargs):
        logger.debug(f"New request PUT with url={url}")
        self.request(method="PUT", url=url, parameters=data, send_result=send_result, **kwargs)

    def delete(self, url: str, data: Union[str, dict, list] = None, send_result: Optional[callable] = None, **kwargs):
        logger.debug(f"New request DELETE with url={url}")
        self.request(method="DELETE", url=url, parameters=data, send_result=send_result, **kwargs)

    def request(
            self,
            method,
            url: str,
            request_retries: int = 1,
            parameters: Union[str, dict, list] = None,
            timeout: int = None,
            send_result: Any = None,
            headers: dict = None
    ):
        self.current_request = {
            "method": method,
            "url": url,
            "request_retries": request_retries,
            "parameters": parameters,
            "send_result": send_result,
            "headers": headers
        }

        if not headers:
            headers = {
                "User-Agent": "MyApp/1.0",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache"
            }

        url = QUrl(url)
        if method == "GET" and parameters:
            query = QUrlQuery()
            for key, value in parameters.items():
                query.addQueryItem(key, value)
            url.setQuery(query)

        elif parameters:
            parameters = bytes(str(json.dumps(parameters)), encoding="utf-8")

        request = QNetworkRequest(url)
        for key, param in headers.items():
            request.setRawHeader(key.encode(), param.encode())

        self.make_request(
            method,
            request,
            request_retries=request_retries,
            send_result=send_result,
            timeout=timeout,
            data=parameters
        )

    def make_request(self, method, request, request_retries, send_result=None, timeout=None, data=None, progress=False):
        if method == "GET" or method == "HEAD":
            reply = self.network_manager.get(request)
        elif method == "POST":
            reply = self.network_manager.post(request, data)
        elif method == "PUT":
            reply = self.network_manager.put(request, data)
        elif method == "DELETE":
            reply = self.network_manager.deleteResource(request)
        else:
            logger.critical(f"Request method {method} not supported.")
            return

        if timeout:
            logger.debug(f"Added time limit for request {timeout} seconds.")
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: (logger.debug("Made request aborting..."), reply.abort()))
            timer.start(timeout * 1000)

        # Connect the finished signal to the function handling the response
        reply.finished.connect(functools.partial(self.handle_response, reply, send_result))
        reply.error.connect(
            functools.partial(
                self.handle_error,
                reply, method, request, request_retries, send_result, timeout, data, progress
            )
        )

        if progress is True:
            reply.metaDataChanged.connect(functools.partial(self.update_total_size, reply))
            reply.downloadProgress.connect(self.handle_progress)
