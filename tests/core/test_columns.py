"""v0.2 の列の操作のテスト（FR-60〜67, 69、受け入れ基準 25〜29。テスト計画書 12 章）。"""

import pytest

from csv_tidy.core.errors import InvalidColumnsError
from csv_tidy.core.models import (
    ColumnSpec,
    FormulaEscaped,
    HeaderRenamed,
    IssueCode,
    Level,
    OutputEncoding,
    RemoveReason,
    RenameReason,
    RowRemoved,
    TidyOptions,
)
from csv_tidy.core.parsing import parse
from csv_tidy.core.service import TidyService
from csv_tidy.core.writing import project, replay_changes
from csv_tidy.core.steps import tidy_names
from helpers import make_csv

service = TidyService()


def export_rows(rows, **options):
    """表を CSV にして整形し、出力した CSV を読み直した表を返す。"""
    data = make_csv(rows)
    exported = service.export(data, TidyOptions(**options))
    return [list(record.cells) for record in parse(exported.decode("utf-8"))]


def result_of(rows, **options):
    return service.tidy(make_csv(rows), TidyOptions(**options))


def spec(source, name=None, keep=True, compare=True):
    return ColumnSpec(source=source, name=name, keep=keep, compare=compare)


def issues_of(result, code):
    return [issue for issue in result.issues if issue.code is code]


def renames_of(result):
    return [c for c in result.changes if isinstance(c, HeaderRenamed)]


# --- 列数と初期の計画（FR-60） ----------------------------------------------------


def test_width_is_the_widest_of_header_and_data_rows():
    """受け入れ基準 26: ヘッダーが 4 列で 5 列の行があると、列数は 5。"""
    result = result_of([["a", "b", "c", "d"], ["1", "2", "3", "4", "5"], ["1", "2", None]])
    assert result.width == 5
    assert result.columns == tuple(spec(source) for source in range(5))


def test_blank_rows_do_not_count_for_width():
    """空行は列数の検査と同じく、列数に数えない（空行だけの列を一覧に出さない）。"""
    result = result_of([["a", "b"], ["", "", "", "", ""], ["1", "2"]])
    assert result.width == 2


def test_column_without_header_is_kept_by_default_and_named():
    """受け入れ基準 26: ヘッダーにない列は初期状態で出力に残る。列名を整える処理で「列5」になる。"""
    rows = export_rows([["a", "b", "c", "d"], ["1", "2", "3", "4", "5"], ["6", "7", "8", "9"]])
    assert rows == [["a", "b", "c", "d", "列5"], ["1", "2", "3", "4", "5"], ["6", "7", "8", "9"]]


def test_column_without_header_has_no_name_when_tidy_names_is_off():
    """列名を整える処理がオフなら、ヘッダーは元のまま（末尾のセルなしは出さない）で、警告する。"""
    rows = [["a", "b"], ["1", "2", "3"]]
    assert export_rows(rows, tidy_names=False) == [["a", "b"], ["1", "2", "3"]]
    issues = issues_of(result_of(rows, tidy_names=False), IssueCode.HEADER_NAME)
    assert [(i.column, i.detail) for i in issues] == [(2, "列名が空です")]


# --- 設定の検査（設計書 V2） -------------------------------------------------------


@pytest.mark.parametrize(
    "sources",
    [
        [0, 1],  # 抜け
        [0, 1, 1],  # 重なり
        [0, 1, 3],  # 範囲外
        [0, 1, 2, 3],  # 多すぎる
    ],
)
def test_columns_must_be_a_permutation(sources):
    with pytest.raises(InvalidColumnsError) as error:
        result_of([["a", "b", "c"], ["1", "2", "3"]], columns=tuple(spec(s) for s in sources))
    assert error.value.width == 3
    assert error.value.code == "invalid_options"


# --- 列の選択・並べ替え（FR-61, FR-62） --------------------------------------------


def test_unchecked_column_is_removed_from_all_rows():
    """受け入れ基準 25・FR-61: 出力しない列は、ヘッダーを含むすべての行から除く。"""
    columns = (spec(0), spec(1, keep=False), spec(2))
    assert export_rows([["a", "b", "c"], ["1", "2", "3"]], columns=columns) == [["a", "c"], ["1", "3"]]


def test_columns_are_output_in_plan_order():
    """受け入れ基準 25・FR-62。"""
    columns = (spec(2), spec(0), spec(1))
    assert export_rows([["a", "b", "c"], ["1", "2", "3"]], columns=columns) == [["c", "a", "b"], ["3", "1", "2"]]


def test_missing_cell_in_the_middle_becomes_empty_and_trailing_is_dropped():
    """設計書 V3: 途中のセルなしは空、末尾のセルなしは出さない。"""
    rows = [["a", "b", "c"], ["1", None], ["4", "5", "6"]]
    # c, a, b の順: 1 行目は c がないので途中が空になる
    assert export_rows(rows, columns=(spec(2), spec(0), spec(1))) == [["c", "a", "b"], ["", "1"], ["6", "4", "5"]]
    # a, c, b の順: 1 行目は c も b もないので、どちらも末尾のセルなしとして出さない
    assert export_rows(rows, columns=(spec(0), spec(2), spec(1))) == [["a", "c", "b"], ["1"], ["4", "6", "5"]]
    # c, b, a の順: 1 行目は c が途中なので空、b は末尾ではない（a がある）ので空
    assert export_rows(rows, columns=(spec(2), spec(1), spec(0))) == [["c", "b", "a"], ["", "", "1"], ["6", "5", "4"]]


def test_project_keeps_row_when_plan_is_identity():
    assert project(["a", "b"], [0, 1, 2]) == ["a", "b"]
    assert project(["a", "", "c"], [0, 1, 2]) == ["a", "", "c"]
    assert project([], [0, 1]) == []


def test_default_options_and_explicit_identity_plan_give_same_output():
    """受け入れ基準 29: 列の操作をしないとき、出力は v0.1 と同じ。"""
    rows = [["名前", "年齢"], ["山田", "30"], ["鈴木"], ["", ""], ["山田", "30"]]
    expected = [["名前", "年齢"], ["山田", "30"], ["鈴木"], ["山田", "30"]]
    assert export_rows(rows) == expected
    assert export_rows(rows, columns=(spec(0), spec(1))) == expected


# --- 名前の変更（FR-63） ------------------------------------------------------------


def test_renamed_column_changes_header_and_is_recorded():
    result = result_of([["a", "b"], ["1", "2"]], columns=(spec(0), spec(1, name="氏名")))
    assert renames_of(result) == [HeaderRenamed(record=0, column=1, before="b", after="氏名", reason=RenameReason.RENAMED)]
    assert export_rows([["a", "b"], ["1", "2"]], columns=(spec(0), spec(1, name="氏名"))) == [["a", "氏名"], ["1", "2"]]


def test_same_name_as_original_is_not_recorded():
    """元の名前（空白を取り除いた後）と同じ名前なら、変更として記録しない。"""
    result = result_of([[" a ", "b"], ["1", "2"]], columns=(spec(0, name="a"), spec(1)))
    assert renames_of(result) == []


def test_name_of_unchecked_column_is_ignored():
    result = result_of([["a", "b"], ["1", "2"]], columns=(spec(0), spec(1, name="x", keep=False)))
    assert renames_of(result) == []


def test_renamed_value_is_escaped_as_formula():
    """名前の変更の後に無害化する（FR-69）。"""
    result = result_of([["a", "b"], ["1", "2"]], columns=(spec(0, name="=x"), spec(1)))
    assert [c for c in result.changes if isinstance(c, FormulaEscaped)] == [
        FormulaEscaped(record=0, column=0, before="=x", after="'=x")
    ]


# --- 重複の判定に使う列（FR-65） ----------------------------------------------------

ID_ROWS = [["ID", "氏名", "電話"], ["1", "山田", "03"], ["2", "山田", "03"]]


def test_rows_differing_only_in_id_are_not_duplicates_by_default():
    """受け入れ基準 27 の前半。"""
    assert issues_of(result_of(ID_ROWS), IssueCode.DUPLICATE) == []


def test_rows_differing_only_in_id_are_duplicates_when_id_is_not_compared():
    """受け入れ基準 27: ID を比べないと重複になり、削除すると最初の行の ID が残る。"""
    columns = (spec(0, compare=False), spec(1), spec(2))
    result = result_of(ID_ROWS, columns=columns)
    assert [(i.record, i.related_record) for i in issues_of(result, IssueCode.DUPLICATE)] == [(2, 1)]
    assert export_rows(ID_ROWS, columns=columns, dedupe=True) == [["ID", "氏名", "電話"], ["1", "山田", "03"]]


def test_missing_cell_and_empty_cell_are_different():
    """FR-65: セルがないことと空のセルは区別する。"""
    rows = [["a", "b"], ["1"], ["1", ""]]
    assert issues_of(result_of(rows, columns=(spec(0), spec(1))), IssueCode.DUPLICATE) == []


def test_no_compared_column_means_no_duplicate_check():
    rows = [["a", "b"], ["1", "2"], ["1", "2"]]
    columns = (spec(0, compare=False), spec(1, compare=False))
    result = result_of(rows, columns=columns, dedupe=True)
    assert issues_of(result, IssueCode.DUPLICATE) == []
    assert not [c for c in result.changes if isinstance(c, RowRemoved)]


def test_unchecked_column_can_be_compared():
    """出力しない列も判定に使える。"""
    rows = [["a", "b"], ["1", "x"], ["1", "y"]]
    columns = (spec(0), spec(1, keep=False, compare=True))
    assert issues_of(result_of(rows, columns=columns), IssueCode.DUPLICATE) == []
    columns = (spec(0), spec(1, keep=False, compare=False))
    result = result_of(rows, columns=columns, dedupe=True)
    assert [(c.record, c.reason, c.duplicate_of) for c in result.changes if isinstance(c, RowRemoved)] == [
        (2, RemoveReason.DUPLICATE, 1)
    ]


# --- 列名を整える（FR-66） ----------------------------------------------------------


def test_header_is_tidied_as_in_acceptance_28():
    """受け入れ基準 28。"""
    rows = [["名前", "", "名前", "住所\n（番地）"], ["山田", "1", "x", "東京"]]
    assert export_rows(rows)[0] == ["名前", "列2", "名前_2", "住所 （番地）"]
    result = result_of(rows)
    assert [(c.column, c.after, c.reason) for c in renames_of(result)] == [
        (1, "列2", RenameReason.TIDIED),
        (2, "名前_2", RenameReason.TIDIED),
        (3, "住所 （番地）", RenameReason.TIDIED),
    ]
    assert result.stats.header_names_tidied == 3


def test_header_is_kept_and_warned_when_tidy_names_is_off():
    """受け入れ基準 28 の後半: オフでは元のまま出力し、空・重複・改行を警告する。"""
    rows = [["名前", "", "名前", "住所\n（番地）"], ["山田", "1", "x", "東京"]]
    assert export_rows(rows, tidy_names=False)[0] == rows[0]
    issues = issues_of(result_of(rows, tidy_names=False), IssueCode.HEADER_NAME)
    assert [(i.level, i.record, i.column, i.detail) for i in issues] == [
        (Level.WARNING, 0, 1, "列名が空です"),
        (Level.WARNING, 0, 2, "列名「名前」がほかの列と重複しています"),
        (Level.WARNING, 0, 3, "列名に改行があります"),
    ]


def test_tidy_names_rules():
    assert tidy_names(["a\r\nb", "c\rd", "e\nf"], [0, 1, 2]) == ["a b", "c d", "e f"]
    # 空の名前の番号は、元のファイルで何列目か（並べ替えた後の位置ではない）
    assert tidy_names(["", "x", ""], [4, 0, 2]) == ["列5", "x", "列3"]
    assert tidy_names(["a", "a", "a"], [0, 1, 2]) == ["a", "a_2", "a_3"]
    # 付けた名前がほかの列名と同じになるときは番号を進める
    assert tidy_names(["a", "a", "a_2"], [0, 1, 2]) == ["a", "a_3", "a_2"]
    # 空の名前を「列N」にした結果がほかの列名と重なると、重複として直す
    assert tidy_names(["列2", ""], [0, 1]) == ["列2", "列2_2"]
    # 改行を直した結果がほかの列名と重なると、重複として直す
    assert tidy_names(["a b", "a\nb"], [0, 1]) == ["a b", "a b_2"]


def test_tidy_names_applies_after_rename_and_selection():
    """FR-66: 列の選択・並べ替え・名前の変更の後の、最終的なヘッダーに対して行う。"""
    rows = [["a", "b", "c"], ["1", "2", "3"]]
    # 出力しない列（b）と同じ名前を付けても重複にならない
    assert export_rows(rows, columns=(spec(0), spec(1, keep=False), spec(2, name="b")))[0] == ["a", "b"]
    # 書き換えた名前がほかの列と重なると、後ろの列に番号が付く
    result = result_of(rows, columns=(spec(2, name="a"), spec(0), spec(1)))
    assert export_rows(rows, columns=(spec(2, name="a"), spec(0), spec(1)))[0] == ["a", "a_2", "b"]
    assert [(c.column, c.after, c.reason) for c in renames_of(result)] == [
        (2, "a", RenameReason.RENAMED),
        (0, "a_2", RenameReason.TIDIED),
    ]


def test_ideal_header_is_not_changed():
    result = result_of([["a", "b"], ["1", "2"]])
    assert renames_of(result) == []
    assert result.stats.header_names_tidied == 0


# --- 出力しない列（FR-67） ----------------------------------------------------------


def test_unchecked_column_is_not_escaped():
    rows = [["a", "b"], ["=1+1", "=2+2"]]
    result = result_of(rows, columns=(spec(0), spec(1, keep=False)))
    assert [(c.record, c.column) for c in result.changes if isinstance(c, FormulaEscaped)] == [(1, 0)]


def test_unchecked_column_is_not_checked_for_cp932():
    rows = [["a", "b"], ["x", "😀"]]
    result = result_of(rows, columns=(spec(0), spec(1, keep=False)), output_encoding=OutputEncoding.CP932)
    assert issues_of(result, IssueCode.UNENCODABLE) == []
    assert result.exportable()
    kept = result_of(rows, output_encoding=OutputEncoding.CP932)
    assert [(i.record, i.column) for i in issues_of(kept, IssueCode.UNENCODABLE)] == [(1, 1)]


def test_unchecked_column_is_still_scanned_for_characters_and_column_count():
    """FR-67: 文字の検査と列数の検査は、出力しない列も対象にする。"""
    rows = [["a", "b"], ["x", "y​", "z"]]
    result = result_of(rows, columns=(spec(0), spec(1, keep=False), spec(2, keep=False)))
    assert [(i.record, i.column) for i in issues_of(result, IssueCode.INVISIBLE_CHAR)] == [(1, 1)]
    assert [i.record for i in issues_of(result, IssueCode.COLUMN_COUNT)] == [1]


# --- 変更の記録を当てはめる手順（設計書 15.5） ---------------------------------------


def test_replay_pads_header_for_column_without_header_and_projects():
    rows = [["a"], ["1", "2", "3"]]
    columns = (spec(2), spec(0), spec(1, keep=False))
    result = result_of(rows, columns=columns)
    assert replay_changes(result) == [["列3", "a"], ["3", "1"]]
    assert export_rows(rows, columns=columns) == [["列3", "a"], ["3", "1"]]
