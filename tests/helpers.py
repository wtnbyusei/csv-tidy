"""テストで使う CSV のバイト列を組み立てる関数（テスト計画書 5.1）。

テストを読むだけで、何を入力しているかが分かるようにするためのもの。
"""

import csv
import io
from collections.abc import Sequence

Row = Sequence[str | None]


def make_csv(
    rows: Sequence[Row] | None = None,
    *,
    encoding: str = "utf-8",
    newline: str = "\n",
    raw: str | None = None,
) -> bytes:
    """CSV のバイト列を作る。

    Args:
        rows: 1 行を値のリストで書いた表。`None` を書いた位置から後ろは
            「セルなし」とし、その行を短くする（例: `["a", "b", None]` は `a,b`）。
        encoding: `utf-8`、`utf-8-sig`（BOM 付き）、`cp932` など。
        newline: 行の区切り。`"\\n"` または `"\\r\\n"`。
        raw: 書き方の誤りを試すときに使う。指定すると `rows` の代わりに、
            この文字列をそのまま `encoding` で変換する（`newline` は使わない）。
    """
    if raw is not None:
        if rows is not None:
            raise ValueError("rows と raw は同時に指定できない")
        return raw.encode(encoding)
    if rows is None:
        raise ValueError("rows か raw のどちらかを指定する")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=newline)
    for row in rows:
        cells = list(row)
        if None in cells:
            cut = cells.index(None)
            if any(cell is not None for cell in cells[cut:]):
                raise ValueError(f"None の後ろに値がある: {row!r}")
            cells = cells[:cut]
        writer.writerow(cells)
    return buffer.getvalue().encode(encoding)
