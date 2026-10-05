"""E2E テスト（テスト計画書 2 章の E）の準備。

アプリを別のスレッドで 127.0.0.1 の空いているポートに起動し、Playwright の Chromium で開く。

    uv sync --group e2e
    uv run playwright install chromium   # 初回だけ
    uv run pytest -m e2e

手元に別の版の Chromium しかないときは、環境変数 E2E_CHROMIUM_PATH にその実行ファイルを指定する。
"""

import importlib.util
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from csv_tidy.api.app import create_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Playwright を入れていない（uv sync だけの）環境では、E2E テストを集めない
if importlib.util.find_spec("playwright") is None:
    collect_ignore_glob = ["test_*.py"]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    """テストの間だけアプリを起動し、その URL を返す。"""
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=_free_port(), log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("テスト用のサーバーが起動しませんでした")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{config.port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def base_url(live_server):
    """page.goto("/") でテスト用のサーバーを開けるようにする（pytest-base-url の値を差し替える）。"""
    return live_server


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    path = os.environ.get("E2E_CHROMIUM_PATH")
    if path:
        return {**browser_type_launch_args, "executable_path": path}
    return browser_type_launch_args


@pytest.fixture
def fixture_path():
    return lambda name: FIXTURES / name
