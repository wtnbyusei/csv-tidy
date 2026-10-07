"""重複の組の示し方・変更の帯の順番・用語の説明（「？」）を、本物のブラウザで確かめる。

画面設計書 4.3（重複の組、帯の中の順番と「他 N」）と 11 章（用語の説明）、テスト計画書 12.5。
"""

import re

import pytest
from playwright.sync_api import Page, expect

from pages import open_file, wait_result

pytestmark = pytest.mark.e2e

# 見本（画面設計書の 10）と同じ形: 2 行目の組（7・12 行目）と、3 行目の組（9 行目）
DUPS = (
    "ID,氏名,電話\n"
    "C001,山田太郎,03-1111\n"
    "C002,佐藤花子,06-3333\n"
    "C003,田中,1\nC004,高橋,2\nC005,鈴木,3\n"
    "C006,山田太郎,03-1111\n"
    "C007,鈴木一郎,052-2222\n"
    "C008,佐藤花子,06-3333\n"
    "C009,伊藤,4\nC010,渡辺,5\n"
    "C011,山田太郎,03-1111\n"
).encode()


def open_dups(page: Page) -> None:
    """DUPS を開き、ID を比べないようにする（ID だけが違う行を重複にする）。"""
    open_file(page, name="dups.csv", data=DUPS)
    wait_result(page)
    page.get_by_label("ID を重複の判定に使う").click()
    wait_result(page)


def before(page: Page, record: int):
    return page.get_by_test_id("diff-before").locator(f'tr[data-record="{record}"]')


def highlighted_lines(page: Page) -> list[str]:
    return page.get_by_test_id("diff-before").locator("tr.grp td.ln").all_text_contents()


def test_duplicate_rows_and_origins_are_shown_by_text(page: Page):
    """重複の行は 1 色で、組は帯の文字で示す。重複の元の行は「変更箇所のみ」にも出る。"""
    open_dups(page)
    gutter = page.get_by_test_id("diff-gutter")
    expect(gutter.locator('tr[data-record="1"] .badge.origin')).to_have_text("重複の元（7・12 行目）")
    expect(gutter.locator('tr[data-record="2"] .badge.origin')).to_have_text("重複の元（9 行目）")
    expect(gutter.locator('tr[data-record="6"] .badge.dup')).to_have_text("重複: 2 行目と同じ")
    expect(before(page, 1)).to_have_class("dup-origin")
    expect(before(page, 6)).to_have_class("dup")


@pytest.mark.parametrize("clicked", [1, 6, 11])
def test_clicking_any_row_of_a_group_highlights_the_whole_group(page: Page, clicked):
    """組のどの行（重複の元・重複の行）を押しても、その組の行をすべて強調する。"""
    open_dups(page)
    before(page, clicked).click()
    assert highlighted_lines(page) == ["2", "7", "12"]
    # 変更の帯と右の表も同じ行を強調する
    expect(page.get_by_test_id("diff-gutter").locator("tr.grp")).to_have_count(3)
    expect(page.get_by_test_id("diff-after").locator("tr.grp")).to_have_count(3)


def test_group_highlight_switches_and_clears(page: Page):
    open_dups(page)
    before(page, 1).click()
    # 別の組の行を押すと、その組に切り替わる
    before(page, 8).click()
    assert highlighted_lines(page) == ["3", "9"]
    # もう一度押すと消える
    before(page, 8).click()
    assert highlighted_lines(page) == []
    # 重複ではない行や表の外を押しても消える
    before(page, 1).click()
    before(page, 7).click()  # 鈴木一郎（重複ではない）
    assert highlighted_lines(page) == []
    before(page, 1).click()
    page.locator("#summary").click()
    assert highlighted_lines(page) == []


def test_group_can_be_toggled_with_keyboard(page: Page):
    """行を Tab キーで選び、Enter キーで強調を切り替えられる。"""
    open_dups(page)
    before(page, 6).focus()
    page.keyboard.press("Enter")
    assert highlighted_lines(page) == ["2", "7", "12"]
    before(page, 6).focus()
    page.keyboard.press("Enter")
    assert highlighted_lines(page) == []


def test_removed_duplicates_keep_red_background_in_group(page: Page):
    """重複行を削除したときも組を強調できる。削除した行は「削除した行」の見た目のまま。"""
    open_dups(page)
    page.get_by_label("重複行を削除する").check()
    wait_result(page)
    before(page, 6).click()
    assert highlighted_lines(page) == ["2", "7", "12"]
    expect(before(page, 6)).to_have_class("removed grp")


def test_group_rows_on_other_pages_are_listed_with_links(page: Page):
    """同じ組の行が今の画面にないときは「同じ組の行」を出し、行番号でその行へ移動できる。"""
    rows = ["名前,値"] + [f"行{i},{i}" for i in range(2, 150)] + ["行2,2"]
    open_file(page, name="long.csv", data=("\n".join(rows) + "\n").encode())
    wait_result(page)
    page.get_by_label("全行").check()
    before(page, 1).click()
    bar = page.get_by_test_id("group-bar")
    expect(bar).to_have_text("同じ組の行: 2・150 行目")
    bar.get_by_role("button", name="150").click()
    expect(page.get_by_test_id("page-position")).to_have_text("2 / 2 ページ")
    expect(page.locator('[data-testid="diff-before"] tr.focus td.ln')).to_have_text("150")
    assert highlighted_lines(page) == ["150"]


def test_gutter_puts_important_badges_first_and_counts_the_rest(page: Page):
    """帯の中は削除 → 重複 → エラー → 警告 → 情報 → 説明の順。収まらない分は「他 N」にする。"""
    data = 'a,b,c\nx,y,z\n" =x","p​q\u007f","1\n2",extra\n'.encode()
    open_file(page, name="many.csv", data=data)
    wait_result(page)
    cell = page.get_by_test_id("diff-gutter").locator('tr[data-record="2"] td')
    texts = cell.locator(".badge, .note-text").all_text_contents()
    # 同じ順位（警告）の中は、課題が見つかった順のまま
    assert texts == [
        "制御文字",
        "見えない文字",
        "列数 4 / 3",
        "数式になる値",
        "複数行のセル",
        "数式を無害化（1 セル）",
        "空白を取り除いた（1 セル）",
    ]
    expect(cell.locator(".more")).to_have_text(re.compile(r"^他 \d+$"))
    expect(cell.locator(".badge").first).to_be_visible()
    expect(cell).to_have_attribute("title", "／".join(texts))


def test_duplicate_badge_comes_before_warnings(page: Page):
    """課題は見えない文字（警告）が先に見つかるが、帯では重複を先に出す。"""
    data = "a,b\nx\u200b,y\n x\u200b,y\n".encode()
    open_file(page, name="dupwarn.csv", data=data)
    wait_result(page)
    cell = page.get_by_test_id("diff-gutter").locator('tr[data-record="2"] td')
    assert cell.locator(".badge, .note-text").all_text_contents() == [
        "重複: 2 行目と同じ",
        "見えない文字",
        "空白を取り除いた（1 セル）",
    ]


def test_help_opens_one_at_a_time_and_closes(page: Page):
    """「？」で説明が出て、もう一度押す・Esc・外を押すと閉じる。一度に 1 つだけ開く。"""
    open_file(page, name="dups.csv", data=DUPS)
    wait_result(page)
    pop = page.locator("#help-pop")
    first = page.get_by_role("button", name="「NBSP」の説明")
    first.click()
    expect(pop).to_contain_text("NBSP")
    expect(pop).to_contain_text("改行しない空白です（U+00A0）")
    expect(first).to_have_attribute("aria-expanded", "true")
    expect(first).to_have_attribute("aria-controls", "help-pop")
    # 説明の「？」を押しても、隣のチェックは変わらない
    expect(page.get_by_role("checkbox", name="セル前後の空白を取り除く")).to_be_checked()

    # 別の「？」を押すと、前の説明は閉じて 1 つだけになる
    second = page.get_by_role("button", name="「列数の警告」の説明").first
    second.click()
    expect(pop).to_have_count(1)
    expect(pop).to_contain_text("ヘッダーの列数と違う")
    expect(first).to_have_attribute("aria-expanded", "false")

    second.click()  # もう一度押すと閉じる
    expect(pop).to_have_count(0)

    second.click()
    page.keyboard.press("Escape")
    expect(pop).to_have_count(0)
    expect(second).to_be_focused()

    second.click()
    page.locator("#summary").click()
    expect(pop).to_have_count(0)


def test_help_text_is_inserted_as_text(page: Page):
    """説明の文字は textContent で入れる（help.js に HTML の書き方があっても実行されない。NFR-07）。"""

    def patched(route):
        body = route.fetch().text().replace(
            "改行しない空白です（U+00A0）。", "<img src=x onerror=window.__xss=1>"
        )
        route.fulfill(body=body, content_type="text/javascript")

    page.route("**/static/help.js", patched)
    open_file(page, name="dups.csv", data=DUPS)
    wait_result(page)
    page.get_by_role("button", name="「NBSP」の説明").click()
    pop = page.locator("#help-pop")
    expect(pop).to_contain_text("<img src=x onerror=window.__xss=1>")
    expect(pop.locator("img")).to_have_count(0)
    assert page.evaluate("window.__xss") is None
