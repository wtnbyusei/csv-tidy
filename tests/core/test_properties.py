"""プロパティベーステスト（テスト計画書 6章）。

ランダムな入力を大量に作り、どんな入力でも成り立つ性質を確かめる。
この作業（コア: 読み込み）で確かめられる P1・P6 の一部を置く。残りは、
トリム・重複の削除・書き出しを作る作業で追加する。
"""

import csv
import io

from hypothesis import given, settings
from hypothesis import strategies as st

from csv_tidy.core.decoding import decode
from csv_tidy.core.errors import TidyError
from csv_tidy.core.models import MAX_BYTES, InputEncoding
from csv_tidy.core.parsing import parse

# CI の仮想マシンは速さが一定でないため、1 件あたりの時間の上限は設けない
settings.register_profile("csv-tidy", deadline=None)
settings.load_profile("csv-tidy")

# セルの値: カンマ・クォート・改行・全角文字・空文字を含む任意の文字列。
# NUL はコアが読み込みの前に拒否する（FR-17）ので含めない。サロゲートは文字列に
# できないので含めない。
cell = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=12,
)
cell_with_specials = st.one_of(cell, st.sampled_from(["", ",", '"', '""', "\n", "\r\n", "\r", "a,b", "山田　太郎"]))
row = st.lists(cell_with_specials, min_size=1, max_size=6)
table = st.lists(row, min_size=1, max_size=8)


def write(rows: list[list[str]], newline: str) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=newline).writerows(rows)
    return buffer.getvalue()


@given(table, st.sampled_from(["\n", "\r\n"]))
def test_p1_written_table_is_parsed_back(rows, newline):
    """P1（一部）: 標準の書き方で書き出した表は、解析すると元の表に戻る。

    書き出しを自前で作る作業（コア: 書き出し）で、書き出し側を自前の処理に置き換える。
    """
    parsed = [list(record.cells) for record in parse(write(rows, newline))]
    assert parsed == rows


@given(st.binary(max_size=200), st.sampled_from([None, *InputEncoding]))
def test_p6_any_bytes_either_parse_or_raise_tidy_error(data, encoding):
    """P6（一部）: どんなバイト列でも、読み込みは結果を返すか TidyError を出すかのどちらか。"""
    assert len(data) <= MAX_BYTES
    try:
        parse(decode(data, encoding).text)
    except TidyError:
        pass


@given(st.binary(max_size=200).map(lambda b: b'"' + b))
def test_p6_quote_heavy_bytes(data):
    """クォートで始まる壊れやすい入力でも、TidyError 以外の例外で止まらない。"""
    try:
        parse(decode(data).text)
    except TidyError:
        pass
