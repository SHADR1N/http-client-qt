import sys
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from QtRequestClient import QtHttpClient, QApplication

# 1) Определяем свой простой handler, который на любой GET отдаёт JSON
class TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(3)
        # формируем тестовый объект
        payload = {
            "status": "ok",
            "message": "Привет от моего тестового сервера!"
        }
        data = json.dumps(payload).encode('utf-8')
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except:
            pass

    # чтобы не засорять консоль логами:
    def log_message(self, format, *args):
        pass


def run_test_server(port=8000):
    server = HTTPServer(('127.0.0.1', port), TestHandler)
    server.serve_forever()

if __name__ == "__main__":
    # 2) Стартуем сервер в фоне
    server_thread = threading.Thread(target=run_test_server, args=(8000,), daemon=True)
    server_thread.start()

    # 3) Запускаем Qt‑приложение и делаем запрос
    app = QApplication([])
    with QtHttpClient(parent=app) as client:
        client.get(
            url="https://github.com/SHADR1N/telespace-application/commits/macos-arm-beta/",
            timeout=5,
            retries=3,
        )
        client.requestCompleted.connect(lambda e: print(e))

    sys.exit(app.exec_())
