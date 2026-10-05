"""プロパティベーステスト（テスト計画書 6章の P1〜P6）。

ランダムな入力を大量に作り、どんな入力でも成り立つ性質を確かめる。
"""

import csv
import io

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from csv_tidy.core.decoding import decode
from csv_tidy.core.errors import TidyError
from csv_tidy.core.models import MAX_BYTES, InputEncoding, Newline, OutputEncoding
from csv_tidy.core.parsing import parse
from csv_tidy.core.writing import write_csv

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
def test_p1_standard_csv_is_parsed_back(rows, newline):
    """P1 の前提: 標準の csv モジュールで書いた表は、解析すると元の表に戻る。"""
    parsed = [list(record.cells) for record in parse(write(rows, newline))]
    assert parsed == rows


def _cp932_ok(value: str) -> bool:
    try:
        value.encode("cp932")
    except UnicodeEncodeError:
        return False
    return True


# 出力の文字コードと、読み直すときの文字コードの組み合わせ。
# 自動判定を使わずに指定するのは、値の先頭が U+FEFF のときに BOM と区別できないため。
_ROUNDTRIP = {
    OutputEncoding.UTF8: InputEncoding.UTF8,
    OutputEncoding.UTF8_BOM: InputEncoding.UTF8_SIG,
    OutputEncoding.CP932: InputEncoding.CP932,
}


@given(table, st.sampled_from(list(OutputEncoding)), st.sampled_from(list(Newline)))
def test_p1_written_table_is_read_back(rows, encoding, newline):
    """P1: どんな値の表でも、自前の書き出しで CSV にして読み直すと、元の表に戻る。"""
    if encoding is OutputEncoding.CP932:
        assume(all(_cp932_ok(value) for row in rows for value in row))
    data = write_csv(rows, encoding, newline)
    parsed = [list(record.cells) for record in parse(decode(data, _ROUNDTRIP[encoding]).text)]
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


# --- 出力と画面の一致（P5）、異常終了しないこと（P6） -----------------------------

from csv_tidy.core.service import TidyService  # noqa: E402
from csv_tidy.core.writing import replay_changes  # noqa: E402

service = TidyService()
messy_cell = st.sampled_from(["", " ", "a", " a", "a　", "\u00a0b", "=x", " =x", "山田", "山田\u200b", "x,y", '"q"', "1\n2"])
messy_table = st.lists(st.lists(messy_cell, min_size=0, max_size=4), min_size=1, max_size=12)
options_strategy = st.builds(
    TidyOptions,
    trim=st.booleans(),
    remove_empty=st.booleans(),
    dedupe=st.booleans(),
    output_encoding=st.sampled_from(list(OutputEncoding)),
    newline=st.sampled_from(list(Newline)),
)


@given(messy_table, options_strategy)
def test_p5_replayed_changes_match_export(rows, options):
    """P5: 元の値に変更の記録を当てはめた表（画面）と、出力した CSV を読み直した表が一致する。"""
    data = write(rows, "\n").encode("utf-8")
    try:
        result = service.tidy(data, options)
        exported = service.export(data, options)
    except TidyError:
        return  # 空行だけなど、処理を中止する入力は対象外（P6 で扱う）
    reread = [list(r.cells) for r in parse(decode(exported, _ROUNDTRIP[options.output_encoding]).text)]
    assert replay_changes(result) == reread


@given(st.binary(max_size=300), options_strategy, st.sampled_from([None, *InputEncoding]))
def test_p6_service_never_fails_unexpectedly(data, options, input_encoding):
    """P6: どんなバイト列でも、整形結果を返すか TidyError を出すかのどちらか。"""
    options = TidyOptions(
        input_encoding=input_encoding,
        trim=options.trim,
        remove_empty=options.remove_empty,
        dedupe=options.dedupe,
        output_encoding=options.output_encoding,
        newline=options.newline,
    )
    try:
        service.tidy(data, options)
        service.export(data, options)
    except TidyError:
        pass

