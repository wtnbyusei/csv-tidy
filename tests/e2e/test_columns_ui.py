"""v0.2 の列の操作の画面を、本物のブラウザで確かめる（テスト計画書 12 章、受け入れ基準 25〜28）。"""

import pytest
from playwright.sync_api import Page, expect

from pages import after_table, download, open_file, wait_result

pytestmark = pytest.mark.e2e

HEADER = ["ID", "名前", "年齢", "住所", "電話", "列6"]


def column_labels(page: Page) -> list[str]:
    """列の一覧の、上から順の列名（入力欄の値。空なら表示している仮の名前）。"""
    names = page.get_by_test_id("column-row").locator("input.name")
    return [value or placeholder for value, placeholder in zip(
        names.evaluate_all("(els) => els.map((e) => e.value)"),
        names.evaluate_all("(els) => els.map((e) => e.placeholder)"),
        strict=True,
    )]


def after_headings(page: Page) -> list[str]:
    return page.get_by_test_id("diff-after").locator("tr").first.locator("th:not(.ln)").all_text_contents()


def open_columns(page: Page, fixture_path) -> None:
    open_file(page, fixture_path("columns.csv"))
    wait_result(page)


def test_headerless_column_is_listed_and_kept(page: Page, fixture_path):
    """受け入れ基準 26・FR-60: ヘッダーにない列が一覧に出て、初期状態では出力に残る。"""
    open_columns(page, fixture_path)
    assert column_labels(page) == ["ID", "名前", "年齢", "住所", "電話", "6 列目（ヘッダーなし）"]
    expect(page.get_by_test_id("conversion")).to_contain_text("列 6 列")
    expect(page.get_by_role("button", name="最初に戻す")).to_be_disabled()
    exported = download(page)
    assert exported[0] == HEADER
    assert exported[2] == ["2", "佐藤花子", "25", "大阪府", "06-3333-4444", "VIP"]


def test_uncheck_move_and_rename_are_reflected_and_reset(page: Page, fixture_path):
    """受け入れ基準 25・FR-61〜64・FR-68: 出力の列とヘッダー、右の表がそのとおりになり、「最初に戻す」で戻る。"""
    open_columns(page, fixture_path)
    page.get_by_label("年齢 を出力する").uncheck()
    wait_result(page)
    # キーボードで「電話」を 1 つ上（「住所」の前）へ移動する
    handle = page.get_by_label("電話 の順番を入れ替える（↑↓ キー）")
    handle.focus()
    page.keyboard.press("ArrowUp")
    wait_result(page)
    expect(page.get_by_label("電話 の順番を入れ替える（↑↓ キー）")).to_be_focused()
    name = page.get_by_label("名前 の出力する列名")
    name.fill("氏名")
    name.press("Enter")
    wait_result(page)

    assert column_labels(page) == ["ID", "氏名", "年齢", "電話", "住所", "6 列目（ヘッダーなし）"]
    expect(page.get_by_test_id("columns").locator(".orig")).to_have_text("← 名前")
    expect(page.get_by_test_id("conversion")).to_contain_text("列 6 列 → 5 列（1 列を出力しない）")
    assert after_headings(page) == ["ID", "氏名 ← 名前", "電話", "住所", "列6 ← 空"]

    page.get_by_label("全行").check()
    exported = download(page)
    assert exported == [
        ["ID", "氏名", "電話", "住所", "列6"],
        ["1", "山田太郎", "03-1111-2222", "東京都"],
        ["2", "佐藤花子", "06-3333-4444", "大阪府", "VIP"],
        ["3", "山田太郎", "03-1111-2222", "東京都"],
        ["4", "鈴木一郎"],
        ["5", "田中次郎", "092-555-6666", "福岡県"],
    ]
    assert after_table(page) == exported

    page.get_by_role("button", name="最初に戻す").click()
    wait_result(page)
    assert column_labels(page) == ["ID", "名前", "年齢", "住所", "電話", "6 列目（ヘッダーなし）"]
    assert after_headings(page) == ["ID", "名前", "年齢", "住所", "電話", "列6 ← 空"]
    expect(page.get_by_role("button", name="最初に戻す")).to_be_disabled()


def test_columns_can_be_moved_by_dragging(page: Page, fixture_path):
    """FR-62: つまみをドラッグして順番を入れ替える。"""
    open_columns(page, fixture_path)
    page.get_by_label("電話 の順番を入れ替える（↑↓ キー）").drag_to(page.get_by_test_id("column-row").first)
    wait_result(page)
    assert column_labels(page)[:2] == ["電話", "ID"]
    assert download(page)[0] == ["電話", "ID", "名前", "年齢", "住所", "列6"]


def test_missing_cell_in_the_middle_is_shown_as_empty(page: Page, fixture_path):
    """設計書 V3・画面設計書 7.3: 並べ替えで行の途中に来たセルなしは、空のセルとして示す。"""
    open_columns(page, fixture_path)
    page.get_by_label("年齢 の順番を入れ替える（↑↓ キー）").focus()
    page.keyboard.press("ArrowDown")  # ID・名前・住所・年齢: 4 行目は住所がなく、年齢はある
    wait_result(page)
    page.get_by_label("全行").check()
    row = page.get_by_test_id("diff-after").locator('tr[data-record="4"]')
    expect(row.locator("td.filled")).to_have_attribute("title", "元はセルなし。空のセルとして出力")
    assert download(page)[4] == ["4", "鈴木一郎", "", "41"]


def test_not_comparing_id_finds_duplicate_and_keeps_first_id(page: Page, fixture_path):
    """受け入れ基準 27・FR-65: ID を比べないと ID だけ違う行が重複になり、削除すると最初の行の ID が残る。"""
    open_columns(page, fixture_path)
    expect(page.get_by_test_id("counts")).to_contain_text("重複 0 件")
    chip = page.get_by_label("ID を重複の判定に使う")
    expect(chip).to_have_attribute("aria-pressed", "true")
    chip.click()
    wait_result(page)
    chip = page.get_by_label("ID を重複の判定に使う")
    expect(chip).to_have_text("比べない")
    expect(chip).to_have_attribute("aria-pressed", "false")
    expect(page.get_by_test_id("counts")).to_contain_text("重複 1 件（未削除）")

    page.get_by_role("tab", name="課題").click()
    expect(page.locator('ul[data-code="duplicate"]')).to_contain_text(
        "4 行目: 2 行目と同じ（比べた列: 名前・年齢・住所・電話・列6）"
    )

    page.get_by_label("重複行を削除する").check()
    wait_result(page)
    exported = download(page)
    assert [row[0] for row in exported] == ["ID", "1", "2", "4", "5"]


def test_header_names_are_tidied_and_warned_when_off(page: Page):
    """受け入れ基準 28・FR-66。"""
    data = '名前,,名前,"住所\n（番地）"\n山田,1,x,東京\n'.encode()
    open_file(page, name="header.csv", data=data)
    wait_result(page)
    assert after_headings(page) == ["名前", "列2 ← 空", "名前_2 ← 名前", "住所 （番地） ← 住所↵（番地）"]
    expect(page.get_by_test_id("counts")).to_contain_text("列名を整えた 3 列")
    expect(page.get_by_test_id("diff-gutter")).to_contain_text("列名を整えた（3 列）")
    assert download(page)[0] == ["名前", "列2", "名前_2", "住所 （番地）"]

    page.get_by_label("列名を整える").uncheck()
    wait_result(page)
    expect(page.get_by_test_id("counts")).not_to_contain_text("列名を整えた")
    assert download(page)[0] == ["名前", "", "名前", "住所\n（番地）"]
    page.get_by_role("tab", name="課題").click()
    expect(page.locator('ul[data-code="header_name"] li')).to_have_text(
        [
            "2 列目: 列名が空です → 差分で見る",
            "3 列目: 列名「名前」がほかの列と重複しています → 差分で見る",
            "4 列目: 列名に改行があります → 差分で見る",
        ]
    )


def test_not_output_column_is_annotated_and_not_checked_for_cp932(page: Page):
    """FR-67: 出力しない列の警告には「（出力しない列）」と添え、CP932 の検査はしない。"""
    data = "名前,メモ\n山田,絵文字😀\n佐藤,a​b\n".encode()
    open_file(page, name="memo.csv", data=data)
    wait_result(page)
    page.locator("#output-encoding").select_option("cp932")
    wait_result(page)
    expect(page.get_by_role("button", name="ダウンロード")).to_be_disabled()

    page.get_by_label("メモ を出力する").uncheck()
    wait_result(page)
    expect(page.get_by_role("button", name="ダウンロード")).to_be_enabled()
    # CP932 で表せない文字があると課題タブに切り替わるので、差分タブに戻して見る
    page.get_by_role("tab", name="差分").click()
    expect(page.get_by_test_id("diff-gutter")).to_contain_text("見えない文字（出力しない列）")
    page.get_by_role("tab", name="課題").click()
    expect(page.locator('ul[data-code="invisible_char"]')).to_contain_text("3 行目・メモの列（出力しない列）")


def test_new_file_starts_from_initial_columns(page: Page, fixture_path):
    """FR-64: 別のファイルを読み込むと、列の一覧は読み込んだときの状態から始まる。"""
    open_columns(page, fixture_path)
    page.get_by_label("年齢 を出力する").uncheck()
    wait_result(page)
    page.locator("#file-input").set_input_files(fixture_path("columns.csv"))
    wait_result(page)
    expect(page.get_by_label("年齢 を出力する")).to_be_checked()
    expect(page.get_by_role("button", name="最初に戻す")).to_be_disabled()


def test_columns_are_reset_when_file_columns_change(page: Page):
    """設計書 V2: 設定を変えてファイルの列数が変わると、列の一覧を最初の状態に戻して知らせる。

    空白だけの行は、空白を取り除くと空行になり列数に数えないが、取り除かないと 3 列の行になる。
    """
    data = "名前,メモ\n山田,a\n  ,  ,  \n".encode()
    open_file(page, name="spaces.csv", data=data)
    wait_result(page)
    page.get_by_label("メモ を出力する").uncheck()
    wait_result(page)
    page.get_by_label("セル前後の空白を取り除く").uncheck()
    wait_result(page)
    expect(page.locator("#columns-notice")).to_have_text("ファイルの列が変わったため、列の一覧を最初の状態に戻しました。")
    assert column_labels(page) == ["名前", "メモ", "3 列目（ヘッダーなし）"]
    expect(page.get_by_label("メモ を出力する")).to_be_checked()


def test_output_line_numbers_ignore_newlines_in_unchecked_columns(page: Page):
    """右の表の行番号は出力するファイルの行番号。出力しない列のセルの中の改行は数えない。"""
    data = '名前,メモ\n山田,"1 行目\n2 行目"\n佐藤,a\n'.encode()
    open_file(page, name="multiline.csv", data=data)
    wait_result(page)
    page.get_by_label("全行").check()
    after = page.get_by_test_id("diff-after")
    expect(after.locator('tr[data-record="2"] td.ln')).to_have_text("4")
    page.get_by_label("メモ を出力する").uncheck()
    wait_result(page)
    expect(after.locator('tr[data-record="2"] td.ln')).to_have_text("3")
