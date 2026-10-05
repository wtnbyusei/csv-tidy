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


# --- 整形処理（P2〜P4） -----------------------------------------------------------

from csv_tidy.core.models import RemoveReason, RowRemoved, TidyOptions  # noqa: E402
from csv_tidy.core.pipeline import run_steps  # noqa: E402
from csv_tidy.core.steps import TRIM_CHARS, trim_cell  # noqa: E402

# 取り除く文字と、取り除かない紛らわしい文字を多めに混ぜる
spacey = st.text(
    alphabet=st.one_of(
        st.sampled_from(list(TRIM_CHARS) + ["\u0085", " ", "​", "\r", "\n", "a", "山"]),
        st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    ),
    max_size=12,
)


@given(spacey)
def test_p2_trim_is_idempotent(value):
    """P2: トリムを 2 回かけても、1 回のときと同じ。"""
    assert trim_cell(trim_cell(value)) == trim_cell(value)


@given(spacey)
def test_p3_trim_removes_only_target_characters_at_both_ends(value):
    """P3: 前後に対象の空白が残らず、それ以外は 1 文字も変わらない。"""
    trimmed = trim_cell(value)
    assert not trimmed.startswith(tuple(TRIM_CHARS))
    assert not trimmed.endswith(tuple(TRIM_CHARS))
    assert trimmed in value  # 前後を削っただけなので、元の値の連続した一部になっている
    head = value[: value.index(trimmed)] if trimmed else value
    assert all(char in TRIM_CHARS for char in head)
    tail = value[value.index(trimmed) + len(trimmed) :] if trimmed else ""
    assert all(char in TRIM_CHARS for char in tail)


small_cell = st.sampled_from(["", "a", "b", " a", "a ", "山田", "山田　"])
data_rows = st.lists(st.lists(small_cell, min_size=1, max_size=3), min_size=1, max_size=15)


@given(data_rows, st.booleans())
def test_p4_no_duplicates_remain_and_order_is_kept(rows, trim):
    """P4: 重複の削除の後は、列数と値が同じ行が 2 つ以上残らない。残った行は元の順番のまま。"""
    text = write([["h1", "h2", "h3"], *rows], "\n")
    ctx = run_steps(parse(text), TidyOptions(trim=trim, dedupe=True, remove_empty=False))
    kept = [tuple(ctx.values[i]) for i in ctx.data_rows() if any(ctx.values[i])]
    assert len(kept) == len(set(kept))
    positions = ctx.data_rows()
    assert positions == sorted(positions)
    # 削除した行は、必ずそれより前に同じ値の行がある
    for change in ctx.changes:
        if isinstance(change, RowRemoved) and change.reason is RemoveReason.DUPLICATE:
            assert change.duplicate_of < change.record
            assert ctx.values[change.duplicate_of] == ctx.values[change.record]
