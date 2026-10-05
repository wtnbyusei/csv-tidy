"""文字コードの判定と変換のテスト（FR-10〜13, FR-17、受け入れ基準 1・10・19）。"""

import codecs

import pytest

from csv_tidy.core.decoding import decode, detect_newline
from csv_tidy.core.errors import DecodeError, EmptyDataError, NotCsvError
from csv_tidy.core.models import InputEncoding, NewlineStyle
from helpers import make_csv

ROWS = [["名前", "住所"], ["山田", "東京都"]]


# --- 自動判定（FR-10, FR-11） --------------------------------------------------


def test_detects_utf8_with_bom():
    decoded = decode(make_csv(ROWS, encoding="utf-8-sig"))
    assert decoded.encoding is InputEncoding.UTF8_SIG
    assert decoded.auto_detected
    assert decoded.text == "名前,住所\n山田,東京都\n"  # BOM は文字列に含めない


def test_detects_utf8_without_bom():
    decoded = decode(make_csv(ROWS, encoding="utf-8"))
    assert decoded.encoding is InputEncoding.UTF8
    assert decoded.text.startswith("名前")


def test_detects_cp932():
    """受け入れ基準 1: CP932 で保存された CSV は CP932 と判定される。"""
    decoded = decode(make_csv(ROWS, encoding="cp932", newline="\r\n"))
    assert decoded.encoding is InputEncoding.CP932
    assert decoded.text == "名前,住所\r\n山田,東京都\r\n"


def test_cp932_only_characters():
    """Windows 独自の文字（①、髙）も CP932 として読める。"""
    decoded = decode(make_csv([["①", "髙橋"]], encoding="cp932"))
    assert decoded.encoding is InputEncoding.CP932
    assert decoded.text == "①,髙橋\n"


def test_ascii_only_is_utf8():
    decoded = decode(b"a,b\n1,2\n")
    assert decoded.encoding is InputEncoding.UTF8


def test_undecodable_bytes_raise_decode_error():
    # 0x81 は CP932 では 2 バイト文字の 1 バイト目なので、次に半角スペース（0x20）が来ると
    # 不正になる。UTF-8 としても不正。
    with pytest.raises(DecodeError) as info:
        decode(b"a,b\n\x81\x20\n")
    assert info.value.encoding is None
    assert info.value.code == "decode_failed"


def test_cp932_reads_bytes_that_are_invalid_in_utf8():
    """Python の CP932 は 0x80 や 0xFD〜0xFF を別の文字として読む（エラーにならない）。

    このようなバイトは文字化けの手がかりとして、文字の検査（FR-18）で警告する。
    """
    decoded = decode(b"a,b\n\x80,\xfd\n")
    assert decoded.encoding is InputEncoding.CP932


def test_bom_followed_by_invalid_utf8_raises_decode_error():
    with pytest.raises(DecodeError):
        decode(codecs.BOM_UTF8 + b"\xff\xfe")


# --- 手動での指定（FR-12） -----------------------------------------------------


def test_manual_encoding_is_used():
    """受け入れ基準 16: 指定した文字コードで読む。"""
    data = make_csv(ROWS, encoding="cp932")
    decoded = decode(data, InputEncoding.CP932)
    assert decoded.encoding is InputEncoding.CP932
    assert not decoded.auto_detected
    assert decoded.text.startswith("名前")


def test_manual_encoding_overrides_auto_detection():
    # ASCII だけなら自動判定では UTF-8 だが、CP932 を指定すればそのとおりに読む
    decoded = decode(b"a,b\n", InputEncoding.CP932)
    assert decoded.encoding is InputEncoding.CP932


def test_wrong_manual_encoding_raises_decode_error():
    data = make_csv(ROWS, encoding="cp932")
    with pytest.raises(DecodeError) as info:
        decode(data, InputEncoding.UTF8)
    assert info.value.encoding == "utf-8"
    assert "utf-8" in info.value.message


# --- 中身がない・CSV ではない（FR-08, FR-17） -----------------------------------


def test_zero_bytes_raise_empty_data_error():
    """受け入れ基準 19: 0 バイトのファイルは「データがありません」。"""
    with pytest.raises(EmptyDataError) as info:
        decode(b"")
    assert info.value.code == "empty_data"
    assert "データがありません" in info.value.message


def test_xlsx_is_rejected_with_guidance():
    """受け入れ基準 10: xlsx は CSV として保存し直すよう案内する。"""
    data = b"PK\x03\x04\x14\x00\x06\x00" + bytes(range(256))
    with pytest.raises(NotCsvError) as info:
        decode(data)
    assert info.value.looks_like_xlsx
    assert "CSV 形式" in info.value.message


def test_xlsx_is_detected_even_with_manual_encoding():
    with pytest.raises(NotCsvError) as info:
        decode(b"PK\x03\x04\x00\x00", InputEncoding.UTF8)
    assert info.value.looks_like_xlsx


def test_nul_character_is_rejected():
    """受け入れ基準 10: NUL 文字を含むファイルは拒否する。"""
    with pytest.raises(NotCsvError) as info:
        decode(b"a,b\n1,\x002\n")
    assert not info.value.looks_like_xlsx
    assert info.value.code == "not_csv"


def test_utf16_without_bom_is_rejected_by_nul():
    # ASCII だけの UTF-16 は UTF-8 として読めてしまうが、NUL を含むので拒否される
    with pytest.raises(NotCsvError):
        decode("name,age\n".encode("utf-16-le"))


# --- 改行コードの判定（FR-47 の変換元） -----------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\nb\n", NewlineStyle.LF),
        ("a\r\nb\r\n", NewlineStyle.CRLF),
        ("a\rb\r", NewlineStyle.CR),
        ("a\r\nb\n", NewlineStyle.MIXED),
        ("a,b", NewlineStyle.NONE),
    ],
)
def test_detect_newline(text, expected):
    assert detect_newline(text) is expected


def test_newline_inside_quoted_cell_is_not_counted():
    # 行の区切りは CRLF。セルの中の LF は数えないので、混在とは判定しない
    assert detect_newline('名前,住所\r\n"1行目\n2行目",x\r\n') is NewlineStyle.CRLF


def test_escaped_quote_does_not_confuse_newline_detection():
    assert detect_newline('a,"He said ""hi""\nok"\r\nb,c\r\n') is NewlineStyle.CRLF


def test_decoded_input_has_source_newline():
    decoded = decode(make_csv(ROWS, newline="\r\n"))
    assert decoded.source_newline is NewlineStyle.CRLF
