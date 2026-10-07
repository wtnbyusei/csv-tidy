"""コアで使うデータの型（設計書 7.1）。"""

from dataclasses import dataclass
from enum import Enum

# ファイルサイズの上限（FR-02）。10MB を 10×1024×1024 バイトとする。
MAX_BYTES = 10 * 1024 * 1024


class InputEncoding(Enum):
    """読み込むときの文字コード（FR-10）。値は Python の codecs の名前。"""

    UTF8_SIG = "utf-8-sig"
    UTF8 = "utf-8"
    CP932 = "cp932"


class NewlineStyle(Enum):
    """元のファイルで使われていた改行コード（FR-47 の「変換元」の表示に使う）。"""

    LF = "lf"
    CRLF = "crlf"
    CR = "cr"
    MIXED = "mixed"  # 2 種類以上が混ざっている
    NONE = "none"  # 改行が 1 つもない（1 行だけのファイル）


@dataclass(frozen=True)
class DecodedInput:
    """文字列に変換した入力。"""

    text: str
    encoding: InputEncoding
    auto_detected: bool
    source_newline: NewlineStyle


@dataclass(frozen=True)
class Record:
    """CSV の 1 件分のデータ。

    `cells` は読み込んだままの値を持つ。`line_start` と `line_end` は元のファイルでの
    行番号（1 から数える）で、セルの中に改行があると 2 つが異なる。
    """

    index: int
    line_start: int
    line_end: int
    cells: tuple[str, ...]

    @property
    def is_multiline(self) -> bool:
        """複数行にまたがるセルを含むか（FR-07）。"""
        return self.line_end > self.line_start


class OutputEncoding(Enum):
    """出力の文字コード（FR-14）。値は API の設定で使う名前。"""

    UTF8 = "utf-8"
    UTF8_BOM = "utf-8-bom"
    CP932 = "cp932"


class Newline(Enum):
    """出力の改行コード（FR-15）。"""

    LF = "lf"
    CRLF = "crlf"


@dataclass(frozen=True)
class ColumnSpec:
    """列の一覧の 1 列分（v0.2、FR-60〜65。設計書 15.1）。

    `source` は元の何列目か（0 から数える）。`name` は出力する列名で、None なら元のヘッダーの値。
    `keep` は出力するか、`compare` は重複の判定に使うか。
    """

    source: int
    name: str | None = None
    keep: bool = True
    compare: bool = True


@dataclass(frozen=True)
class TidyOptions:
    """利用者が選ぶ設定（設計書 11.1）。初期値は要件定義書 4.3 のとおり。"""

    input_encoding: InputEncoding | None = None  # None なら自動で判定する
    trim: bool = True
    remove_empty: bool = True
    dedupe: bool = False  # 意図的な重複を消さないよう、初期状態はオフ（FR-22）
    escape_formulas: bool = True  # 安全のため、初期状態はオン（FR-49、要件定義書 1.1）
    output_encoding: OutputEncoding = OutputEncoding.UTF8
    newline: Newline = Newline.LF
    # 列の一覧の最終形（v0.2、FR-60〜65）。None なら読み込んだときの状態（全列を元の順番で出力し、すべて比べる）
    columns: tuple[ColumnSpec, ...] | None = None
    tidy_names: bool = True  # 列名を整える（FR-66）。初期状態はオン


class RemoveReason(Enum):
    """行を削除した理由。"""

    LEADING_BLANK = "leading_blank"  # ヘッダーより前の空行（FR-04）
    EMPTY = "empty"  # 空行（FR-21）
    DUPLICATE = "duplicate"  # 重複行（FR-22）


@dataclass(frozen=True)
class Change:
    """整形処理による変更の記録（FR-41）。`record` は Record.index。"""

    record: int


@dataclass(frozen=True)
class CellTrimmed(Change):
    """セルの前後の空白を取り除いた（FR-20）。"""

    column: int
    before: str
    after: str


@dataclass(frozen=True)
class FormulaEscaped(Change):
    """表計算ソフトで数式として扱われないよう、値の先頭に `'` を付けた（FR-49）。"""

    column: int
    before: str
    after: str


class RenameReason(Enum):
    """列名を変えた理由（v0.2）。"""

    RENAMED = "renamed"  # 利用者が書き換えた（FR-63）
    TIDIED = "tidied"  # 列名を整える処理で直した（FR-66）


@dataclass(frozen=True)
class HeaderRenamed(Change):
    """ヘッダー行のセル（元の `column` 列目）の値を変えた。列名の変更を表す（設計書 15.3）。

    ヘッダーにない列の名前を決めたときは、`before` は空。
    """

    column: int
    before: str
    after: str
    reason: RenameReason


@dataclass(frozen=True)
class RowRemoved(Change):
    """行を削除した。重複のときは `duplicate_of` に最初の行の Record.index を入れる。"""

    reason: RemoveReason
    duplicate_of: int | None = None


class Level(Enum):
    """課題の重さ。ERROR があると出力できない。"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueCode(Enum):
    """課題の種類（設計書 11.2 の issues の code）。"""

    COLUMN_COUNT = "column_count"  # 列数がヘッダーと違う（FR-30, 31）
    CONTROL_CHAR = "control_char"  # 制御文字（FR-18）
    INVISIBLE_CHAR = "invisible_char"  # 見えない文字（FR-18）
    MULTILINE_CELL = "multiline_cell"  # 複数行にまたがるセル（FR-07）
    FORMULA_LIKE = "formula_like"  # 整形で数式のような値になった（FR-48）
    LEADING_BLANK = "leading_blank"  # 先頭の空行を飛ばした（FR-04）
    NO_DATA_ROWS = "no_data_rows"  # ヘッダー行だけ（FR-08）
    DUPLICATE = "duplicate"  # 重複がある（削除していない）（FR-22）
    UNENCODABLE = "unencodable"  # 出力の文字コードで表せない文字（FR-16）
    HEADER_NAME = "header_name"  # 列名が空・重複・改行を含む（列名を整える処理がオフのとき。FR-66）


@dataclass(frozen=True)
class Issue:
    """利用者に知らせる課題。

    `record` と `column` は対象の場所（ファイル全体に関わるときは None）。
    `related_record` は関係する別の行（重複の最初の行など）の Record.index。
    """

    level: Level
    code: IssueCode
    detail: str
    record: int | None = None
    column: int | None = None
    related_record: int | None = None


@dataclass(frozen=True)
class Stats:
    """変更と課題の件数（FR-46）。画面上部の概要に表示する。"""

    cells_trimmed: int = 0
    empty_removed: int = 0
    duplicates_found: int = 0  # 見つかった重複の数（削除したものを含む）
    duplicates_removed: int = 0
    column_warnings: int = 0
    control_chars: int = 0
    invisible_chars: int = 0
    formula_warnings: int = 0
    unencodable_chars: int = 0
    formulas_escaped: int = 0
    header_names_tidied: int = 0


@dataclass(frozen=True)
class TidyResult:
    """整形結果（設計書 7.1）。

    整形後の値は持たない。`records`（元の値）に `changes`（変更の記録）を当てはめて
    求める（設計書 D2）。`header_record` はヘッダー行の Record.index。
    """

    input: DecodedInput
    options: TidyOptions
    records: list[Record]
    header_record: int
    changes: list[Change]
    issues: list[Issue]
    stats: Stats
    width: int = 0  # 列数（ヘッダーと空行以外のデータ行のうち、いちばん多い列数。FR-60）
    columns: tuple[ColumnSpec, ...] = ()  # 実際に使った列の計画（設計書 15.4）

    def exportable(self) -> bool:
        """レベルが ERROR の課題がなければ出力できる（FR-16）。"""
        return not any(issue.level is Level.ERROR for issue in self.issues)

