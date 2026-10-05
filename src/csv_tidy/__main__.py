"""`uv run csv-tidy` で、この PC からだけ接続できるサーバーを起動する。"""

import uvicorn

from csv_tidy.api.app import create_app

# 自分の PC からだけ接続できるようにする（NFR-02）。外部に公開しない。
HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    """サーバーを起動する。"""
    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
