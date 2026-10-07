"""画面の主要な流れを、本物のブラウザ（Chromium）で確かめる（テスト計画書 9 章の E）。

見た目の細部は手動確認（テスト計画書 7 章）で確かめる。
"""

import csv
import io

import pytest
from playwright.sync_api import Page, expect

from csv_tidy.core.models import MAX_BYTES
from pages import before_row, open_file, wait_result

pytestmark = pytest.mark.e2e


# ---- 主要な流れ（FR-01, 40〜47） ----


def test_main_flow_shows_summary_diff_and_issues(page: Page, fixture_path):
    open_file(page, fixture_path("customers_cp932.csv"))
    wait_result(page)

    # 概要: 変換（FR-47）と件数（FR-46）
    conversion = page.get_by_test_id("conversion")
    expect(conversion).to_contain_text("CP932（自動判定） → UTF-8")
    expect(conversion).to_contain_text("改行 CRLF → LF")
    counts = page.get_by_test_id("counts")
    expect(counts).to_contain_text("空白を取り除いた 2 セル")
    expect(counts).to_contain_text("空行の削除 1 行")
    expect(counts).to_contain_text("重複 1 件（未削除）")
    expect(counts).to_contain_text("列数の警告 1")
    expect(page.locator("#input-encoding option").first).to_have_text("自動判定（CP932 と判定）")
    expect(page.locator("#dedupe-note")).to_have_text("重複が 1 件あります（まだ削除していません）")

    # 差分: 変更の帯（FR-43）
    gutter = page.get_by_test_id("diff-gutter")
    expect(gutter).to_contain_text("削除: 空行")
    expect(gutter).to_contain_text("列数 3 / 4")
    expect(gutter).to_contain_text("重複: 2 行目と同じ")
    expect(gutter).to_contain_text("空白を取り除いた（1 セル）")

    # 変更前は取り除いた空白を印で示し、変更後は取り除いた値（FR-42, 43）
    row = before_row(page, "3")
    expect(row.locator("td.trimmed .ws.full")).to_have_count(1)
    after = page.get_by_test_id("diff-after").locator('tr[data-record="2"] td.trimmed')
    expect(after).to_have_text("佐藤花子")
    # 削除した行は、変更後では「出力しない」
    expect(page.get_by_test_id("diff-after").locator('tr[data-record="3"]')).to_have_text("（出力しない）")
    # セルなし（FR-45）
    expect(before_row(page, "5").locator("td.missing")).to_have_text("セルなし")

    # 前後の変更への移動（FR-44）。重複の元の行（2 行目）も変更のある行に数える（画面設計書 4.3）
    position = page.get_by_test_id("change-position")
    expect(position).to_have_text("変更 ― / 7")
    page.get_by_role("button", name="次の変更 ▶").click()
    expect(position).to_have_text("変更 1 / 7")
    expect(page.locator('[data-testid="diff-before"] tr.focus td.ln')).to_have_text("2")
    page.get_by_role("button", name="次の変更 ▶").click()
    expect(position).to_have_text("変更 2 / 7")
    expect(page.locator('[data-testid="diff-before"] tr.focus td.ln')).to_have_text("3")

    # 全行はページに分ける（FR-44）
    page.get_by_label("全行").check()
    expect(page.get_by_test_id("page-position")).to_have_text("1 / 10 ページ")
    expect(page.get_by_test_id("diff-before").locator("tr")).to_have_count(101)

    # 課題タブから差分の行へ移動する（画面設計書 4.4）
    page.get_by_role("tab", name="課題（3）").click()
    page.get_by_role("button", name="5 行目: 列数 3（ヘッダーは 4） → 差分で見る").click()
    expect(page.get_by_role("tab", name="差分")).to_have_attribute("aria-selected", "true")
    expect(page.locator('[data-testid="diff-before"] tr.focus td.ln')).to_have_text("5")


def test_drag_and_drop_reads_file(page: Page):
    page.goto("/")
    data_transfer = page.evaluate_handle(
        """() => {
            const dt = new DataTransfer();
            dt.items.add(new File(["名前,年齢\\n 山田 ,30\\n"], "drop.csv", { type: "text/csv" }));
            return dt;
        }"""
    )
    page.get_by_test_id("dropzone").dispatch_event("drop", {"dataTransfer": data_transfer})
    wait_result(page)
    expect(page.locator("#file-name")).to_have_text("drop.csv")
    expect(page.get_by_test_id("counts")).to_contain_text("空白を取り除いた 1 セル")


def test_after_table_matches_downloaded_csv(page: Page, fixture_path):
    """画面で組み立てた変更後の値（設計書 D2）が、ダウンロードした CSV と一致する。"""
    open_file(page, fixture_path("customers_cp932.csv"))
    wait_result(page)
    page.get_by_label("全行").check()

    shown = []
    for row in page.get_by_test_id("diff-after").locator("tr[data-record]:not(.placeholder)").all():
        cells = row.locator("td:not(.ln):not(.missing)").all_text_contents()
        shown.append(cells)

    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    exported = list(csv.reader(io.StringIO(info.value.path().read_bytes().decode("utf-8"), newline="")))

    # 1 ページ目の 100 行のうち、空行の 1 行は出力しない
    assert len(shown) == 99
    assert shown == exported[: len(shown)]


# ---- 受け入れ基準 9: 1000 行中 999 行目だけの変更が「変更箇所のみ」に表示される ----


def test_change_on_line_999_of_1000_is_shown(page: Page):
    lines = ["名前,番号"] + [f"name{i},{i}" for i in range(2, 1001)]
    lines[998] = "name999 ,999"  # 999 行目（0 から数えて 998）だけ後ろに空白
    open_file(page, name="large.csv", data=("\n".join(lines) + "\n").encode())
    wait_result(page)

    expect(before_row(page, "999").locator("td.trimmed")).to_have_count(1)
    expect(page.get_by_test_id("diff-before")).to_contain_text("… 変更のない 995 行を省略 …")
    expect(page.get_by_test_id("change-position")).to_have_text("変更 ― / 1")
    # 変更の件数にも反映される
    expect(page.get_by_test_id("counts")).to_contain_text("空白を取り除いた 1 セル")


# ---- ダウンロード（FR-50, 受け入れ基準 23） ----


def test_download_is_named_after_original_file(page: Page, fixture_path):
    open_file(page, name="顧客一覧.csv", data=fixture_path("customers_cp932.csv").read_bytes())
    wait_result(page)
    expect(page.locator("#download-name")).to_have_text("顧客一覧_tidy.csv")

    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    assert info.value.suggested_filename == "顧客一覧_tidy.csv"
    content = info.value.path().read_bytes()
    assert content.startswith("名前,年齢,住所,電話\n".encode())


@pytest.mark.parametrize(("name", "expected"), [("data.txt", "data_tidy.csv"), ("data", "data_tidy.csv")])
def test_download_name_drops_any_extension(page: Page, name, expected):
    open_file(page, name=name, data="a,b\n1,2\n".encode())
    wait_result(page)
    expect(page.locator("#download-name")).to_have_text(expected)


# ---- 大きさの確認（FR-02） ----


def test_too_large_file_is_rejected_before_sending(page: Page):
    sent = []
    page.on("request", lambda request: sent.append(request.url) if "/api/" in request.url else None)
    open_file(page, name="big.csv", data=b"a" * (MAX_BYTES + 1))

    expect(page.locator("#error-title")).to_have_text("ファイルが大きすぎます")
    expect(page.locator("#error-code")).to_have_text("エラーの種類: file_too_large")
    assert sent == []


# ---- 文字コードの指定（FR-12, 受け入れ基準 16） ----


def test_manual_input_encoding_rereads_file(page: Page, fixture_path):
    open_file(page, fixture_path("customers_cp932.csv"))
    wait_result(page)

    page.locator("#input-encoding").select_option("utf-8")
    expect(page.locator("#error-title")).to_have_text("指定した文字コードで読み込めません")

    page.locator("#input-encoding").select_option("cp932")
    wait_result(page)
    expect(page.get_by_test_id("conversion")).to_contain_text("CP932（指定） → UTF-8")


# ---- CP932 で表せない文字（FR-16, 受け入れ基準 11） ----


def test_unencodable_characters_disable_download(page: Page, fixture_path):
    open_file(page, fixture_path("emoji.csv"))
    wait_result(page)
    expect(page.get_by_role("button", name="ダウンロード")).to_be_enabled()

    page.locator("#output-encoding").select_option("cp932")
    expect(page.get_by_role("tab", name="課題（2）")).to_have_attribute("aria-selected", "true")
    expect(page.get_by_role("button", name="ダウンロード")).to_be_disabled()
    expect(page.locator("#export-reason")).to_contain_text("CP932 で表せない文字が 2 件あります")
    expect(page.get_by_test_id("counts")).to_contain_text("CP932 で表せない文字 2")
    errors = page.locator('details[data-level="error"]')
    expect(errors).to_contain_text("2 行目・名前の列: 「😀」（U+1F600）は CP932 で表せません")
    expect(errors).to_contain_text("2 行目・メモの列: 「—」（U+2014）は CP932 で表せません")

    # 差分で該当する文字を囲む
    errors.get_by_role("button", name="2 行目・名前の列: 「😀」（U+1F600）は CP932 で表せません → 差分で見る").click()
    expect(page.get_by_test_id("diff-after").locator(".unenc-char").first).to_have_text("😀")

    # UTF-8 に戻すとダウンロードできる
    page.locator("#output-encoding").select_option("utf-8")
    expect(page.get_by_role("button", name="ダウンロード")).to_be_enabled()


# ---- 値を文字として表示する（NFR-07, 受け入れ基準 12） ----


def test_html_in_values_is_shown_as_text(page: Page, fixture_path):
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    open_file(page, fixture_path("xss.csv"))
    wait_result(page)
    page.get_by_label("全行").check()

    before = page.get_by_test_id("diff-before")
    expect(before).to_contain_text("<script>alert(1)</script>")
    expect(before).to_contain_text("<img src=x onerror=alert(1)>")
    expect(page.get_by_test_id("diff").locator("script, img, b")).to_have_count(0)
    assert dialogs == []


# ---- 差分で強調・記号として見えるもの（受け入れ基準 13・14、FR-48, FR-18） ----


def test_formula_like_and_invisible_characters_are_marked_in_diff(page: Page, fixture_path):
    open_file(page, fixture_path("manual_check.csv"))
    wait_result(page)
    before = page.get_by_test_id("diff-before")
    gutter = page.get_by_test_id("diff-gutter")
    after = page.get_by_test_id("diff-after")

    # 基準 13: 空白を取ると数式になるセルだけを強調する。元から数式の値は強調しない
    expect(after.locator("td.formula")).to_have_count(1)
    expect(after.locator("td.formula")).to_have_text("'=1+1")  # 初期状態では無害化もする（FR-49）
    expect(gutter.locator(".badge", has_text="数式になる値")).to_have_count(1)

    # 基準 14: ゼロ幅スペースは記号で見え、見た目が同じ行どうしは重複にならない
    expect(before.locator(".mark", has_text="ZWSP")).to_have_count(1)
    expect(gutter.locator('tr[data-record="6"]')).to_contain_text("見えない文字")
    expect(gutter.locator('tr[data-record="7"]')).not_to_contain_text("重複")
    # DEL と C1 制御文字も警告し、記号で見える
    expect(before.locator(".mark", has_text="DEL")).to_have_count(1)
    expect(before.locator(".mark", has_text="U+0085")).to_have_count(1)
    expect(gutter.locator(".badge", has_text="制御文字")).to_have_count(2)


# ---- 数式の無害化（FR-49、受け入れ基準 24） ----


def test_formulas_are_escaped_by_default_and_can_be_turned_off(page: Page):
    data = "名前,メモ\n=1+1,-5\n＝SUM(A1),ok\n".encode()
    open_file(page, name="formula.csv", data=data)
    wait_result(page)

    after = page.get_by_test_id("diff-after")
    expect(after.locator("td.escaped")).to_have_text(["'=1+1", "'＝SUM(A1)"])
    expect(page.get_by_test_id("counts")).to_contain_text("数式を無害化 2 セル")
    expect(page.get_by_test_id("diff-gutter")).to_contain_text("数式を無害化（1 セル）")
    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    assert info.value.path().read_bytes().decode() == "名前,メモ\n'=1+1,-5\n'＝SUM(A1),ok\n"

    # オフにすると値は変わらない
    page.get_by_label("数式として扱われる値を無害化する").uncheck()
    wait_result(page)
    expect(after.locator("td.escaped")).to_have_count(0)
    expect(page.get_by_test_id("counts")).not_to_contain_text("数式を無害化")
    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    assert info.value.path().read_bytes().decode() == "名前,メモ\n=1+1,-5\n＝SUM(A1),ok\n"


def test_column_without_header_is_named_and_matches_download(page: Page):
    """受け入れ基準 26・設計書 15.5: ヘッダーにない列は名前を付けて残し、右の表とダウンロードが一致する。

    初期状態の計画では列名の変更は列の順に記録されるので、空のセルを足す手順（列の並べ替えで起きる）は
    作業18 の列の一覧のテストで確かめる。
    """
    data = "名前,年齢\n山田,30,東京\n鈴木,41\n".encode()
    open_file(page, name="wide.csv", data=data)
    wait_result(page)
    page.get_by_label("全行").check()

    shown = [
        row.locator("td:not(.ln):not(.missing)").all_text_contents()
        for row in page.get_by_test_id("diff-after").locator("tr[data-record]:not(.placeholder)").all()
    ]
    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    exported = list(csv.reader(io.StringIO(info.value.path().read_bytes().decode("utf-8"), newline="")))
    assert exported == [["名前", "年齢", "列3"], ["山田", "30", "東京"], ["鈴木", "41"]]
    assert shown == exported


# ---- 先頭の空行（受け入れ基準 20） ----


def test_leading_blank_rows_are_reported_and_not_exported(page: Page):
    open_file(page, name="leading.csv", data="\n,,\n名前,年齢\n山田,30\n".encode())
    wait_result(page)
    page.get_by_role("tab", name="課題（1）").click()
    expect(page.locator("#panel-issues")).to_contain_text("先頭の空行 2 行を飛ばしました")

    page.get_by_role("tab", name="差分").click()
    expect(page.get_by_test_id("diff-gutter")).to_contain_text("削除: 先頭の空行")
    with page.expect_download() as info:
        page.get_by_role("button", name="ダウンロード").click()
    assert info.value.path().read_bytes() == "名前,年齢\n山田,30\n".encode()


# ---- 処理を中止するエラー（画面設計書 6 章） ----


@pytest.mark.parametrize(
    ("name", "title", "message"),
    [
        ("broken_quote.csv", "CSV の書き方に誤りがあります", "3 行目から始まるデータの書き方に誤りがあります"),
        ("not_csv.xlsx", "Excel のファイルです", "CSV 形式を選んで保存し直してください"),
    ],
)
def test_errors_are_explained(page: Page, fixture_path, name, title, message):
    open_file(page, fixture_path(name))
    expect(page.locator("#error-title")).to_have_text(title)
    expect(page.locator("#error-message")).to_contain_text(message)
    expect(page.get_by_role("button", name="ダウンロード")).to_be_disabled()


@pytest.mark.parametrize(("name", "data"), [("zero.csv", b""), ("blank.csv", b"\r\n\r\n,,\r\n")])
def test_empty_files_are_rejected(page: Page, name, data):
    """受け入れ基準 19: 0 バイトと空行だけのファイルは「データがありません」になる。"""
    open_file(page, name=name, data=data)
    expect(page.locator("#error-title")).to_have_text("データがありません")
    expect(page.locator("#error-message")).to_contain_text("データがありません。")


# ---- 設定を続けて変えると、最後の設定の結果だけを表示する（画面設計書 5 章） ----


def test_last_option_change_wins(page: Page, fixture_path):
    open_file(page, fixture_path("customers_cp932.csv"))
    wait_result(page)
    trim = page.get_by_label("セル前後の空白を取り除く")
    trim.uncheck()
    trim.check()
    trim.uncheck()
    wait_result(page)
    expect(page.get_by_test_id("counts")).to_contain_text("空白を取り除いた 0 セル")


# ---- 画面の幅 1280px での表示（手動確認 M3・M4 で見つけた不具合の回帰テスト。設計書 I30・I31） ----


def test_four_columns_and_long_line_numbers_fit_at_1280px(page: Page, fixture_path):
    page.set_viewport_size({"width": 1280, "height": 860})
    open_file(page, fixture_path("customers_cp932.csv"))
    wait_result(page)
    side = page.get_by_test_id("diff-before").locator(".side")
    # 4 列の表が、横にスクロールしなくても収まる
    assert side.evaluate("(el) => el.scrollWidth <= el.clientWidth")
    # 「812〜813」の行番号が切れない
    line = before_row(page, "812〜813").locator("td.ln")
    assert line.evaluate("(el) => el.scrollWidth <= el.clientWidth")


def test_important_badge_is_visible_in_narrow_change_column(page: Page, fixture_path):
    page.set_viewport_size({"width": 1280, "height": 860})
    open_file(page, fixture_path("manual_check.csv"))
    wait_result(page)
    # 「空白を取り除いた」と同じ行にあっても、「数式になる値」のバッジが帯の中に見えている
    cell = page.get_by_test_id("diff-gutter").locator('tr[data-record="4"] td')
    badge = cell.locator(".badge", has_text="数式になる値")
    cell_box, badge_box = cell.bounding_box(), badge.bounding_box()
    assert badge_box["x"] + badge_box["width"] <= cell_box["x"] + cell_box["width"]
