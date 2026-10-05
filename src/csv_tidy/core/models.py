"""コアで使うデータの型（設計書 7.1）。

この作業（コア: 読み込み）で使う型だけを置く。設定・変更記録・課題・結果の型は、
それを使う作業で追加する。
"""

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
