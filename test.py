import sys

from QtRequestClient import QtHttpClient, QApplication

app = QApplication([])

# with QtHttpClient(parent=app) as client:
#     client.get(url="https://script.googleusercontent.com/macros/echo?user_content_key=xALHHk9bfBevJp6ne9N6aw494fVahHiO8cIcyGqRd2kgt83zBlW7Ibb17EwgnFipHY6ogxvdiPgpKujZlxLyjf2q5ArNGrJvm5_BxDlH2jW0nuo2oDemN9CCS2h10ox_1xSncGQajx_ryfhECjZEnJ9GRkcRevgjTvo8Dc32iw_BLJPcPfRdVKhJT5HNzQuXEeN3QFwl2n0M6ZmO-h7C6bwVq0tbM60-YSRgvERRRx91eQMV9hTntRGQmSuaYtHQ&lib=MwxUjRcLr2qLlnVOLh12wSNkqcO1Ikdrk", request_retries=3, send_result=lambda e: print(e))
#     client.get(url="https://telegram.org/", request_retries=3, send_result=lambda e: print("Telegram completed."))

with QtHttpClient(parent=app) as client:
    client.get(
        url="https://github.com/SHADR1N/http-client-qt/commits/main/",
        send_result=lambda e: print(e.json),
        timeout=5,
        request_retries=3
    )

sys.exit(app.exec_())
