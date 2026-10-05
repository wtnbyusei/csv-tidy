"""CSV の書き出しのテスト（FR-14, FR-15, FR-16、受け入れ基準 1・11）。"""

import pytest

from csv_tidy.core.models import IssueCode, Level, Newline, OutputEncoding, TidyOptions
from csv_tidy.core.parsing import parse
from csv_tidy.core.pipeline import run_steps
from csv_tidy.core.writing import write_csv

ROWS = [["名前", "メモ"], ["山田", "1行目\n2行目"], ["鈴木", 'He said "hi", ok']]


def test_utf8_lf():
    data = write_csv(ROWS, OutputEncoding.UTF8, Newline.LF)
    assert data == '名前,メモ\n山田,"1行目\n2行目"\n鈴木,"He said ""hi"", ok"\n'.encode()


def test_utf8_bom_crlf_starts_with_bom_and_uses_crlf():
    """受け入れ基準 1: 先頭が EF BB BF で、行の区切りがすべて CRLF。"""
    data = write_csv([["名前"], ["山田"]], OutputEncoding.UTF8_BOM, Newline.CRLF)
    assert data.startswith(b"\xef\xbb\xbf")
    assert data == b"\xef\xbb\xbf" + "名前\r\n山田\r\n".encode()


def test_cp932():
    data = write_csv([["名前"], ["髙橋①"]], OutputEncoding.CP932, Newline.CRLF)
    assert data == "名前\r\n髙橋①\r\n".encode("cp932")


def test_newline_inside_cell_is_kept_when_crlf_is_chosen():
    """要件定義書 7.1: 改行コードの指定は行の区切りにだけ使い、セルの中の改行は変えない。"""
    data = write_csv([["a\nb"]], OutputEncoding.UTF8, Newline.CRLF)
    assert data == b'"a\nb"\r\n'


def test_quotes_only_where_needed():
    data = write_csv([["a", "b c", "", "x,y"]], OutputEncoding.UTF8, Newline.LF)
    assert data == b'a,b c,,"x,y"\n'


def test_short_rows_keep_their_length():
    """FR-31: 列数は変えずに出力する。"""
    data = write_csv([["h1", "h2", "h3"], ["a"], []], OutputEncoding.UTF8, Newline.LF)
    assert data == b"h1,h2,h3\na\n\n"


def test_unencodable_character_raises():
    with pytest.raises(UnicodeEncodeError):
        write_csv([["😀"]], OutputEncoding.CP932, Newline.LF)


# --- CP932 で表せない文字の検査（FR-16） ------------------------------------------


def unencodable_issues(text, encoding):
    ctx = run_steps(parse(text), TidyOptions(output_encoding=encoding))
    return [i for i in ctx.issues if i.code is IssueCode.UNENCODABLE]


def test_unencodable_characters_are_errors_with_position():
    """受け入れ基準 11: 絵文字や — があると、場所と文字が ERROR として返る。"""
    issues = unencodable_issues("名前,メモ\n山田😀,a—b\n", OutputEncoding.CP932)
    assert [(i.level, i.record, i.column) for i in issues] == [
        (Level.ERROR, 1, 0),
        (Level.ERROR, 1, 1),
    ]
    assert "U+1F600" in issues[0].detail
    assert "U+2014" in issues[1].detail


def test_cp932_characters_are_not_errors():
    assert unencodable_issues("h\n髙橋①〜\n", OutputEncoding.CP932) == []


@pytest.mark.parametrize("encoding", [OutputEncoding.UTF8, OutputEncoding.UTF8_BOM])
def test_utf8_output_does_not_check(encoding):
    assert unencodable_issues("h\n😀\n", encoding) == []


def test_removed_rows_are_not_checked():
    # 重複として削除される行や、トリムで消える空白の位置は、出力に含まれないので調べない
    ctx = run_steps(parse("h\nx\n"), TidyOptions(output_encoding=OutputEncoding.CP932))
    assert ctx.issues == []
    issues = unencodable_issues("h\n,　\n", OutputEncoding.CP932)  # 全角スペースは CP932 で表せる
    assert issues == []


def test_same_character_in_a_cell_is_one_issue():
    assert len(unencodable_issues("h\n😀😀\n", OutputEncoding.CP932)) == 1


def test_unencodable_in_header_is_checked():
    issues = unencodable_issues("名前😀\nx\n", OutputEncoding.CP932)
    assert [i.record for i in issues] == [0]
