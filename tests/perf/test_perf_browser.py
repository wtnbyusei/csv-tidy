"""ファイルを選んでから差分が画面に出るまでの時間を測る（NFR-01、受け入れ基準 21）。"""

import time

import pytest
from playwright.sync_api import Page

from .conftest import DATA, LIMIT_SECONDS, REPEAT

pytestmark = pytest.mark.perf


def test_time_until_diff_is_shown(page: Page, bench_data, report):
    page.goto("/")
    report.notes["ブラウザ"] = f"Chromium {page.context.browser.version}（Playwright、画面なしで実行）"
    seconds = []
    for _ in range(REPEAT):
        # 毎回、画面を開き直して同じ条件にする
        page.reload()
        start = time.perf_counter()
        page.locator("#file-input").set_input_files(DATA)
        page.locator('[data-testid="diff-before"] tr[data-record]').first.wait_for(timeout=60_000)
        seconds.append(time.perf_counter() - start)
    report.add("ファイルを選んでから差分が出るまで（画面）", seconds)
    assert max(seconds) < LIMIT_SECONDS
