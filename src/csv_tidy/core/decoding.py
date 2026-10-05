"""文字コードの判定と、文字列への変換（FR-10〜13, FR-17）。"""

import codecs
import re

from .errors import DecodeError, EmptyDataError, NotCsvError
from .models import DecodedInput, InputEncoding, NewlineStyle

# Excel の .xlsx は ZIP 形式で、先頭がこの 4 バイトになる
_ZIP_MAGIC = b"PK\x03\x04"

# クォートで囲まれた部分。「""」は 2 つの囲みが続いたものとして扱われるので、
# 正しい CSV ならセルの中身だけを取り除ける。
_QUOTED = re.compile(r'"[^"]*"')

# 自動判定で試す順番（FR-11）。BOM 付き UTF-8 は BOM があるときだけ試す。
_AUTO_ORDER = (InputEncoding.UTF8, InputEncoding.CP932)


def decode(data: bytes, encoding: InputEncoding | None = None) -> DecodedInput:
    """バイト列を文字列に変換する。

    Args:
        data: アップロードされたファイルの中身。
        encoding: 利用者が指定した文字コード。`None` なら自動で判定する。

    Raises:
        EmptyDataError: 0 バイトのとき。
        NotCsvError: xlsx（ZIP 形式）のとき、または変換した結果に NUL 文字があるとき。
        DecodeError: 文字列に変換できないとき。
    """
    if not data:
        raise EmptyDataError()
    # 文字コードの判定より先に確かめる。xlsx は変換に失敗することがあり、
    # そうなると「文字コードを判定できない」という分かりにくいエラーになるため。
    if data.startswith(_ZIP_MAGIC):
        raise NotCsvError(looks_like_xlsx=True)

    if encoding is None:
        text, used = _auto_decode(data)
        auto = True
    else:
        try:
            text = data.decode(encoding.value)
        except UnicodeDecodeError:
            raise DecodeError(encoding=encoding.value) from None
        used, auto = encoding, False

    if "\x00" in text:
        raise NotCsvError(looks_like_xlsx=False)

    return DecodedInput(
        text=text,
        encoding=used,
        auto_detected=auto,
        source_newline=detect_newline(text),
    )


def _auto_decode(data: bytes) -> tuple[str, InputEncoding]:
    if data.startswith(codecs.BOM_UTF8):
        try:
            return data.decode(InputEncoding.UTF8_SIG.value), InputEncoding.UTF8_SIG
        except UnicodeDecodeError:
            raise DecodeError() from None
    for candidate in _AUTO_ORDER:
        try:
            return data.decode(candidate.value), candidate
        except UnicodeDecodeError:
            continue
    raise DecodeError()


def detect_newline(text: str) -> NewlineStyle:
    """行の区切りに使われている改行コードを調べる。

    クォートで囲まれたセルの中の改行は、行の区切りではないので数えない。
    """
    text = _QUOTED.sub("", text)
    crlf = text.count("\r\n")
    cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    kinds = [style for style, n in ((NewlineStyle.CRLF, crlf), (NewlineStyle.CR, cr), (NewlineStyle.LF, lf)) if n]
    if not kinds:
        return NewlineStyle.NONE
    if len(kinds) > 1:
        return NewlineStyle.MIXED
    return kinds[0]
