"""コアの入口（設計書 7.2 の TidyService）。API はここだけを呼ぶ。"""

from .decoding import decode
from .errors import UnencodableError
from .models import (
    CellTrimmed,
    IssueCode,
    RemoveReason,
    RowRemoved,
    Stats,
    TidyOptions,
    TidyResult,
)
from .parsing import parse
from .pipeline import run_steps
from .steps import TidyContext
from .writing import write_csv


class TidyService:
    """バイト列と設定を受け取り、整形結果や出力ファイルを返す。状態は持たない（NFR-08）。"""

    def tidy(self, data: bytes, options: TidyOptions) -> TidyResult:
        """整形結果を返す（画面の表示用）。

        Raises:
            TidyError の仲間: 処理を中止するとき（データなし、CSV ではない、
                文字コードを判定できない、書き方の誤り）。
        """
        result, _ = self._run(data, options)
        return result

    def export(self, data: bytes, options: TidyOptions) -> bytes:
        """整形後の CSV のバイト列を返す（ダウンロード用）。

        Raises:
            UnencodableError: 出力の文字コードで表せない文字があるとき（FR-16）。
            TidyError の仲間: tidy() と同じ。
        """
        result, ctx = self._run(data, options)
        if not result.exportable():
            raise UnencodableError(count=result.stats.unencodable_chars)
        # 出力は作業用の値から作る。画面は変更の記録から組み立てる（両者の一致はテスト P5）
        rows = [ctx.values[position] for position in ctx.output_rows()]
        return write_csv(rows, options.output_encoding, options.newline)

    @staticmethod
    def _run(data: bytes, options: TidyOptions) -> tuple[TidyResult, TidyContext]:
        decoded = decode(data, options.input_encoding)
        ctx = run_steps(parse(decoded.text), options)
        assert ctx.header is not None  # HeaderStep がヘッダーを決めるか、例外を出している
        result = TidyResult(
            input=decoded,
            options=options,
            records=ctx.records,
            header_record=ctx.header,
            changes=ctx.changes,
            issues=ctx.issues,
            stats=compute_stats(ctx),
        )
        return result, ctx


def compute_stats(ctx: TidyContext) -> Stats:
    """変更と課題から件数を数える（FR-46）。"""
    removed = [c.reason for c in ctx.changes if isinstance(c, RowRemoved)]
    codes = [issue.code for issue in ctx.issues]
    duplicates_removed = removed.count(RemoveReason.DUPLICATE)
    return Stats(
        cells_trimmed=sum(isinstance(c, CellTrimmed) for c in ctx.changes),
        empty_removed=removed.count(RemoveReason.EMPTY),
        duplicates_found=duplicates_removed + codes.count(IssueCode.DUPLICATE),
        duplicates_removed=duplicates_removed,
        column_warnings=codes.count(IssueCode.COLUMN_COUNT),
        control_chars=codes.count(IssueCode.CONTROL_CHAR),
        invisible_chars=codes.count(IssueCode.INVISIBLE_CHAR),
        formula_warnings=codes.count(IssueCode.FORMULA_LIKE),
        unencodable_chars=codes.count(IssueCode.UNENCODABLE),
    )
