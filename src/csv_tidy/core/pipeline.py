"""整形処理を決まった順番で実行する（設計書 7.2、FR-24）。"""

from collections.abc import Sequence

from .models import Record, TidyOptions
from .steps import (
    CharScanStep,
    ColumnCountStep,
    ColumnPlanStep,
    DataRowsStep,
    DedupeStep,
    EmptyRowStep,
    EncodabilityStep,
    FormulaEscapeStep,
    FormulaStep,
    HeaderNameStep,
    HeaderStep,
    Step,
    TidyContext,
    TrimStep,
)


def default_steps() -> list[Step]:
    """処理の順番（設計書 9 章のアクティビティ図、v0.2 は 15.2 節）。

    文字の検査は元の値に対して行う。空行の判定と重複の比較は、トリムの後の値で行う。
    列の計画はヘッダーを決めた直後に決める（重複の判定が比べる列を使うため）。
    列名の変更と列名を整える処理は、データ行への処理の後に行う（FR-69）。
    無害化は、数式化の検査（整形で数式のような値になったかを、無害化の前の値で調べる）の後、
    出力の文字コードの検査の前に行う（FR-24, FR-69）。
    """
    return [
        CharScanStep(),
        TrimStep(),
        HeaderStep(),
        ColumnPlanStep(),
        EmptyRowStep(),
        ColumnCountStep(),
        DedupeStep(),
        FormulaStep(),
        DataRowsStep(),
        HeaderNameStep(),
        FormulaEscapeStep(),
        EncodabilityStep(),
    ]


class Pipeline:
    """Step を順番に実行する。"""

    def __init__(self, steps: Sequence[Step] | None = None) -> None:
        self.steps = list(steps) if steps is not None else default_steps()

    def run(self, ctx: TidyContext) -> None:
        for step in self.steps:
            step.apply(ctx)


def run_steps(records: Sequence[Record], options: TidyOptions) -> TidyContext:
    """レコードに整形処理をかけ、結果の作業領域を返す。"""
    ctx = TidyContext(records=list(records), options=options)
    Pipeline().run(ctx)
    return ctx
