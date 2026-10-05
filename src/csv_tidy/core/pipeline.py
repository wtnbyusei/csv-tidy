"""整形処理を決まった順番で実行する（設計書 7.2、FR-24）。"""

from collections.abc import Sequence

from .models import Record, TidyOptions
from .steps import (
    CharScanStep,
    ColumnCountStep,
    DataRowsStep,
    DedupeStep,
    EmptyRowStep,
    EncodabilityStep,
    FormulaStep,
    HeaderStep,
    Step,
    TidyContext,
    TrimStep,
)


def default_steps() -> list[Step]:
    """v0.1 の処理の順番（設計書 9 章のアクティビティ図）。

    文字の検査は元の値に対して行う。空行の判定と重複の比較は、トリムの後の値で行う。
    """
    return [
        CharScanStep(),
        TrimStep(),
        HeaderStep(),
        EmptyRowStep(),
        ColumnCountStep(),
        DedupeStep(),
        FormulaStep(),
        DataRowsStep(),
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
