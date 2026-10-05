"""コアの入口のテスト（FR-14〜16, FR-46, NFR-08、受け入れ基準 1・11・17・22）。"""

import pytest

from csv_tidy.core.errors import CsvSyntaxError, EmptyDataError, UnencodableError
from csv_tidy.core.models import (
    InputEncoding,
    IssueCode,
    Newline,
    NewlineStyle,
    OutputEncoding,
    Stats,
    TidyOptions,
)
from csv_tidy.core.service import TidyService
from csv_tidy.core.writing import replay_changes
from helpers import make_csv

service = TidyService()

SAMPLE = make_csv(
    [
        ["名前", "年齢", "住所", "電話"],
        ["山田太郎", "30", "東京都", "03-1111-2222"],
        ["  佐藤花子　", "25", "大阪府", "06-3333-4444"],
        ["", "", "", ""],
        ["鈴木一郎", "41", "愛知県", None],
        ["田中​次郎", "28", "福岡県", "092-555-6666"],
        ["山田太郎", "30", "東京都", "03-1111-2222"],
    ],
    # ゼロ幅スペース（U+200B）は CP932 で表せないので、UTF-8（BOM 付き）で作る
    encoding="utf-8-sig",
    newline="\r\n",
)


def test_tidy_returns_result_with_input_info():
    result = service.tidy(SAMPLE, TidyOptions())
    assert result.input.encoding is InputEncoding.UTF8_SIG
    assert result.input.auto_detected
    assert result.input.source_newline is NewlineStyle.CRLF
    assert result.header_record == 0
    assert len(result.records) == 7
    assert result.exportable()


def test_cp932_input_is_detected_and_exported_as_utf8_bom():
    """受け入れ基準 1: CP932 の CSV は CP932 と判定され、BOM 付き UTF-8・CRLF で出力できる。"""
    data = make_csv([["名前", "住所"], ["髙橋", "東京都"]], encoding="cp932", newline="\r\n")
    options = TidyOptions(output_encoding=OutputEncoding.UTF8_BOM, newline=Newline.CRLF)
    assert service.tidy(data, options).input.encoding is InputEncoding.CP932
    assert service.export(data, options) == b"\xef\xbb\xbf" + "名前,住所\r\n髙橋,東京都\r\n".encode()


def test_stats_count_changes_and_issues():
    """FR-46: 件数は変更の記録と課題から数える。"""
    result = service.tidy(SAMPLE, TidyOptions())
    assert result.stats == Stats(
        cells_trimmed=1,
        empty_removed=1,
        duplicates_found=1,
        duplicates_removed=0,
        column_warnings=1,
        control_chars=0,
        invisible_chars=1,
        formula_warnings=0,
        unencodable_chars=0,
    )


def test_stats_with_dedupe_on():
    result = service.tidy(SAMPLE, TidyOptions(dedupe=True))
    assert (result.stats.duplicates_found, result.stats.duplicates_removed) == (1, 1)


def test_export_utf8_bom_crlf():
    """受け入れ基準 1: BOM 付き UTF-8 と CRLF で出力する。"""
    data = service.export(SAMPLE, TidyOptions(output_encoding=OutputEncoding.UTF8_BOM, newline=Newline.CRLF))
    assert data.startswith(b"\xef\xbb\xbf")
    text = data[3:].decode("utf-8")
    assert text.count("\r\n") == text.count("\n")  # 改行はすべて CRLF
    assert text.splitlines() == [
        "名前,年齢,住所,電話",
        "山田太郎,30,東京都,03-1111-2222",
        "佐藤花子,25,大阪府,06-3333-4444",
        "鈴木一郎,41,愛知県",
        "田中​次郎,28,福岡県,092-555-6666",
        "山田太郎,30,東京都,03-1111-2222",
    ]


def test_export_matches_replayed_changes():
    """画面が変更の記録から組み立てる表と、出力ファイルの中身が一致する（設計書 D2）。"""
    options = TidyOptions(dedupe=True)
    result = service.tidy(SAMPLE, options)
    exported = service.export(SAMPLE, options).decode("utf-8").splitlines()
    assert [",".join(row) for row in replay_changes(result)] == exported


@pytest.mark.parametrize(
    ("options", "expected_rows"),
    [
        (TidyOptions(trim=False), 6),
        (TidyOptions(remove_empty=False), 7),
        (TidyOptions(dedupe=True), 5),
    ],
)
def test_each_option_changes_only_its_own_processing(options, expected_rows):
    """受け入れ基準 17: 各処理をオフ（重複はオン）にすると、その処理の結果だけが変わる。"""
    result = service.tidy(SAMPLE, options)
    assert len(replay_changes(result)) == expected_rows


def test_trim_off_keeps_spaces_in_export():
    data = service.export(SAMPLE, TidyOptions(trim=False)).decode("utf-8")
    assert "  佐藤花子　" in data


def test_unencodable_makes_result_not_exportable():
    """受け入れ基準 11: CP932 出力で絵文字があると出力できず、件数が返る。"""
    data = make_csv([["名前"], ["山田😀"], ["佐藤—"]])
    options = TidyOptions(output_encoding=OutputEncoding.CP932)
    result = service.tidy(data, options)
    assert not result.exportable()
    assert result.stats.unencodable_chars == 2
    assert [i.code for i in result.issues] == [IssueCode.UNENCODABLE, IssueCode.UNENCODABLE]
    with pytest.raises(UnencodableError) as info:
        service.export(data, options)
    assert info.value.count == 2
    assert info.value.code == "unencodable"


def test_same_data_switched_to_utf8_is_exportable():
    data = make_csv([["名前"], ["山田😀"]])
    assert service.export(data, TidyOptions(output_encoding=OutputEncoding.UTF8)).decode() == "名前\n山田😀\n"


def test_manual_input_encoding_is_used():
    result = service.tidy(b"a,b\n", TidyOptions(input_encoding=InputEncoding.CP932))
    assert result.input.encoding is InputEncoding.CP932
    assert not result.input.auto_detected


def test_errors_stop_processing():
    with pytest.raises(EmptyDataError):
        service.tidy(b"", TidyOptions())
    with pytest.raises(EmptyDataError):
        service.tidy(b"\n,,\n", TidyOptions())
    with pytest.raises(CsvSyntaxError):
        service.export(b'h\n"a\n', TidyOptions())


def test_service_keeps_no_state_between_calls():
    """NFR-08: 同じデータを設定だけ変えて 2 回処理すると、それぞれ独立した結果になる。"""
    first = service.tidy(SAMPLE, TidyOptions(dedupe=True))
    second = service.tidy(SAMPLE, TidyOptions())
    assert first.stats.duplicates_removed == 1
    assert second.stats.duplicates_removed == 0
    assert first.records == second.records
