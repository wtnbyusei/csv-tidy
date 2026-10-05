"""CSV の解析とヘッダー行の決定のテスト（FR-03〜08, FR-25、受け入れ基準 7・19・20）。"""

import pytest

from csv_tidy.core.errors import CsvSyntaxError
from csv_tidy.core.parsing import find_header, is_blank, parse


def cells_of(text):
    return [record.cells for record in parse(text)]


# --- RFC 4180 に沿った解析（FR-03, FR-25） --------------------------------------


def test_basic_rows():
    assert cells_of("名前,年齢\n山田,30\n") == [("名前", "年齢"), ("山田", "30")]


def test_comma_inside_quotes_is_part_of_cell():
    """受け入れ基準 7: クォートの中のカンマは 1 つのセルとして読む。"""
    assert cells_of('"Yes, I am",x\n') == [("Yes, I am", "x")]


def test_escaped_double_quote():
    assert cells_of('"He said ""hi""",x\n') == [('He said "hi"', "x")]


def test_newline_inside_quotes_is_part_of_cell():
    assert cells_of('a,"1行目\n2行目"\n') == [("a", "1行目\n2行目")]


def test_crlf_inside_quotes_is_kept():
    assert cells_of('a,"1行目\r\n2行目"\r\n') == [("a", "1行目\r\n2行目")]


def test_empty_cell_and_quoted_empty_cell_are_the_same():
    """FR-25: `a,,b` と `a,"",b` は同じ。"""
    assert cells_of('a,,b\na,"",b\n') == [("a", "", "b"), ("a", "", "b")]


def test_short_row_keeps_its_cell_count():
    """セルが省略された行は、短いまま読む（FR-31 の前提）。"""
    assert cells_of("h1,h2,h3,h4\na,b\na,b,,\n") == [
        ("h1", "h2", "h3", "h4"),
        ("a", "b"),
        ("a", "b", "", ""),
    ]


def test_blank_line_becomes_record_with_no_cells():
    assert cells_of("h\n\nx\n") == [("h",), (), ("x",)]


def test_last_line_without_newline():
    assert cells_of("a,b\n1,2") == [("a", "b"), ("1", "2")]


def test_cr_only_line_endings():
    assert cells_of("a,b\r1,2\r") == [("a", "b"), ("1", "2")]


def test_quote_in_middle_of_unquoted_cell_is_kept_as_text():
    """クォートで始まらないセルの中の `"` は文字として扱う（H2 で確認した動き）。"""
    assert cells_of('a,b"c,d\n') == [("a", 'b"c', "d")]


def test_empty_text_has_no_records():
    assert parse("") == []


# --- 行番号と複数行のセル（FR-07） ---------------------------------------------


def test_line_numbers():
    records = parse('h1,h2\n"a\nb",c\nd,e\n')
    assert [(r.index, r.line_start, r.line_end) for r in records] == [
        (0, 1, 1),
        (1, 2, 3),
        (2, 4, 4),
    ]


def test_multiline_record_is_marked():
    records = parse('h\n"1行目\n2行目\n3行目"\nx\n')
    assert [r.is_multiline for r in records] == [False, True, False]
    assert (records[1].line_start, records[1].line_end) == (2, 4)


# --- 長いセル（FR-06） ----------------------------------------------------------


def test_cell_longer_than_default_csv_limit():
    long_value = "あ" * 200_000  # csv モジュールの既定の上限 131,072 文字を超える
    assert cells_of(f'h\n"{long_value}"\n')[1] == (long_value,)


# --- 書き方の誤り（FR-05） ------------------------------------------------------


def test_unclosed_quote_reports_starting_line():
    """受け入れ基準 7: 3 行目でクォートを閉じ忘れると、3 行目をエラーとして返す。"""
    with pytest.raises(CsvSyntaxError) as info:
        parse('h1,h2\na,b\n"c,d\ne,f\ng,h\n')
    assert info.value.line == 3
    assert info.value.code == "csv_syntax"
    assert "3 行目" in info.value.message


def test_character_after_closing_quote_is_error():
    """受け入れ基準 7: `"c"x,d` はその行でエラーになる。"""
    with pytest.raises(CsvSyntaxError) as info:
        parse('h1,h2\na,b\n"c"x,d\ne,f\n')
    assert info.value.line == 3


def test_error_in_first_record_reports_line_1():
    with pytest.raises(CsvSyntaxError) as info:
        parse('"h1\n')
    assert info.value.line == 1


def test_error_after_multiline_record_reports_correct_line():
    # 2〜3 行目が 1 つのレコード。誤りは 4 行目から始まるレコード
    with pytest.raises(CsvSyntaxError) as info:
        parse('h\n"a\nb"\n"c"x\n')
    assert info.value.line == 4


# --- 空行とヘッダー行の決定（FR-04, FR-08） --------------------------------------


@pytest.mark.parametrize(
    ("cells", "expected"),
    [((), True), (("",), True), (("", "", ""), True), (("", "a"), False), ((" ",), False)],
)
def test_is_blank(cells, expected):
    assert is_blank(cells) is expected


def test_header_is_first_row_when_not_blank():
    assert find_header([("名前",), ("山田",)]) == 0


def test_leading_blank_rows_are_skipped():
    """受け入れ基準 20: 先頭の空行 2 行を飛ばし、3 行目がヘッダーになる。"""
    rows = [record.cells for record in parse("\n,,\n名前,年齢\n山田,30\n")]
    assert find_header(rows) == 2


def test_whitespace_only_row_is_not_blank_without_trim():
    # トリムが無効なら、空白だけの行は空ではない（トリム後の値を渡すのは呼び出し側）
    assert find_header([(" ", " "), ("名前",)]) == 0


def test_all_blank_returns_none():
    """受け入れ基準 19: 空行だけなら、ヘッダーが見つからない（呼び出し側でエラーにする）。"""
    assert find_header([(), ("", ""), ()]) is None
    assert find_header([]) is None
