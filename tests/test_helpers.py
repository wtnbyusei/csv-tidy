"""テスト用の関数 make_csv 自体が正しく動くかを確かめる。"""

import pytest

from helpers import make_csv


def test_utf8_lf():
    assert make_csv([["名前", "年齢"], ["山田", "30"]]) == "名前,年齢\n山田,30\n".encode()


def test_cp932_crlf():
    data = make_csv([["名前"], ["山田"]], encoding="cp932", newline="\r\n")
    assert data == "名前\r\n山田\r\n".encode("cp932")


def test_utf8_bom():
    assert make_csv([["a"]], encoding="utf-8-sig").startswith(b"\xef\xbb\xbf")


def test_quotes_comma_and_newline_in_cell():
    data = make_csv([["Yes, I am", 'He said "hi"', "1行目\n2行目"]])
    assert data.decode() == '"Yes, I am","He said ""hi""","1行目\n2行目"\n'


def test_none_makes_row_shorter():
    data = make_csv([["h1", "h2", "h3", "h4"], ["a", "b", None, None], ["a", "b", "", ""]])
    assert data.decode() == "h1,h2,h3,h4\na,b\na,b,,\n"


def test_none_followed_by_value_is_rejected():
    with pytest.raises(ValueError):
        make_csv([["a", None, "c"]])


def test_raw_is_used_as_is():
    assert make_csv(raw='h1,h2\n"a,b\n') == b'h1,h2\n"a,b\n'


def test_rows_and_raw_together_is_rejected():
    with pytest.raises(ValueError):
        make_csv([["a"]], raw="a\n")


def test_neither_rows_nor_raw_is_rejected():
    with pytest.raises(ValueError):
        make_csv()
