"""E2E テストで使う、画面の操作と読み取りの道具。"""

import csv
import io
import re

from playwright.sync_api import Page, expect


def open_file(page: Page, path=None, *, name=None, data: bytes | None = None) -> None:
    """画面を開き、ファイルを選ぶ。data を渡したときは、その中身のファイルを name の名前で選ぶ。"""
    page.goto("/")
    if data is None:
        page.locator("#file-input").set_input_files(path)
    else:
        page.locator("#file-input").set_input_files({"name": name, "mimeType": "text/csv", "buffer": data})


def wait_result(page: Page) -> None:
    expect(page.locator("#view-result")).to_be_visible()
    expect(page.locator("#view-loading")).to_be_hidden()


def before_row(page: Page, line: str):
    return page.get_by_test_id("diff-before").locator("tr").filter(has=page.locator("td.ln", has_text=re.compile(f"^{line}$")))


def after_table(page: Page) -> list[list[str]]:
    """右の表（変更後）の各行の値。斜線の「セルなし」は出力しないので除く。"""
    rows = page.get_by_test_id("diff-after").locator("tr[data-record]:not(.placeholder)").all()
    return [row.locator("td:not(.ln):not(.missing)").all_text_contents() for row in rows]


def download(page: Page) -> list[list[str]]:
    """「ダウンロード」を押し、保存された CSV（UTF-8）を読んだ表を返す。"""
    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    return list(csv.reader(io.StringIO(info.value.path().read_bytes().decode("utf-8"), newline="")))
