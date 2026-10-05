"""処理を中止するときの例外（設計書 7.2、11.3）。

`code` は API がエラー応答に入れる種類の名前。`message` は画面に出す日本語の説明。
"""


class TidyError(Exception):
    """コアが処理を中止するときの例外の基底クラス。"""

    code = "tidy_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EmptyDataError(TidyError):
    """中身がない（0 バイト、または空行だけ）（FR-08）。"""

    code = "empty_data"

    def __init__(self) -> None:
        super().__init__("データがありません。中身のある CSV ファイルを選んでください。")


class NotCsvError(TidyError):
    """CSV ではないファイル（FR-17）。"""

    code = "not_csv"

    def __init__(self, *, looks_like_xlsx: bool) -> None:
        if looks_like_xlsx:
            message = (
                "Excel のファイル（.xlsx）のようです。"
                "Excel で開き、「名前を付けて保存」で CSV 形式を選んで保存し直してください。"
            )
        else:
            message = "CSV ではないファイルのようです（文字ではないデータが含まれています）。"
        super().__init__(message)
        self.looks_like_xlsx = looks_like_xlsx


class DecodeError(TidyError):
    """どの文字コードでも文字に変換できない、または指定した文字コードで変換できない（FR-12, FR-13）。"""

    code = "decode_failed"

    def __init__(self, *, encoding: str | None = None) -> None:
        if encoding is None:
            message = (
                "文字コードを判定できませんでした。"
                "UTF-8 か Shift_JIS（CP932）で保存した CSV ファイルを選んでください。"
            )
        else:
            message = (
                f"指定した文字コード（{encoding}）では読み込めませんでした。"
                "別の文字コードを選ぶか、「自動判定」に戻してください。"
            )
        super().__init__(message)
        self.encoding = encoding


class CsvSyntaxError(TidyError):
    """CSV の書き方の誤り（FR-05）。`line` は問題のレコードが始まる行番号（1 から数える）。"""

    code = "csv_syntax"

    def __init__(self, *, line: int, detail: str) -> None:
        super().__init__(
            f"{line} 行目から始まるデータの書き方に誤りがあります。"
            "「\"」（ダブルクォート）が閉じられていないか、閉じた「\"」の直後に余分な文字がないか確認してください。"
        )
        self.line = line
        self.detail = detail


class UnencodableError(TidyError):
    """出力の文字コードで表せない文字があり、出力できない（FR-16）。"""

    code = "unencodable"

    def __init__(self, *, count: int) -> None:
        super().__init__(
            f"出力の文字コード（CP932）で表せない文字が {count} 件あります。"
            "課題の一覧で場所を確認し、元のデータを直すか、出力の文字コードを UTF-8 にしてください。"
        )
        self.count = count

