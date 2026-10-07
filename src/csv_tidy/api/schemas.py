"""API で受け渡す JSON の形（設計書 11.1・11.2）。

設定（options）は pydantic で値を確かめる。整形結果は行数が多くなりうるので、
pydantic の型に詰め直さず、そのまま辞書にして返す（速さのため）。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from csv_tidy.core.models import (
    CellTrimmed,
    Change,
    ColumnSpec,
    FormulaEscaped,
    HeaderRenamed,
    InputEncoding,
    Issue,
    Newline,
    OutputEncoding,
    RowRemoved,
    TidyOptions,
    TidyResult,
)


class ColumnIn(BaseModel):
    """列の一覧の 1 列分（設計書 15.1）。`compare` を書かなければ `keep` と同じにする。"""

    model_config = ConfigDict(extra="forbid")

    source: int = Field(ge=0)
    name: str | None = None
    keep: bool = True
    compare: bool | None = None

    def to_core(self) -> ColumnSpec:
        compare = self.keep if self.compare is None else self.compare
        return ColumnSpec(source=self.source, name=self.name, keep=self.keep, compare=compare)


class OptionsIn(BaseModel):
    """設定（設計書 11.1）。書かれていない項目は初期値になる。知らない項目はエラーにする。"""

    model_config = ConfigDict(extra="forbid")

    input_encoding: InputEncoding | None = None
    trim: bool = True
    remove_empty: bool = True
    dedupe: bool = False
    escape_formulas: bool = True
    output_encoding: OutputEncoding = OutputEncoding.UTF8
    newline: Newline = Newline.LF
    columns: list[ColumnIn] | None = None
    tidy_names: bool = True

    def to_core(self) -> TidyOptions:
        return TidyOptions(
            input_encoding=self.input_encoding,
            trim=self.trim,
            remove_empty=self.remove_empty,
            dedupe=self.dedupe,
            escape_formulas=self.escape_formulas,
            output_encoding=self.output_encoding,
            newline=self.newline,
            columns=None if self.columns is None else tuple(column.to_core() for column in self.columns),
            tidy_names=self.tidy_names,
        )


def result_to_json(result: TidyResult, size: int) -> dict[str, Any]:
    """整形結果を、設計書 11.2 の形の辞書にする。"""
    return {
        "input": {
            "encoding": result.input.encoding.value,
            "auto_detected": result.input.auto_detected,
            "newline": result.input.source_newline.value,
            "size": size,
        },
        "output": {
            "encoding": result.options.output_encoding.value,
            "newline": result.options.newline.value,
            "exportable": result.exportable(),
        },
        "header_record": result.header_record,
        "width": result.width,
        "columns": [{"source": c.source, "keep": c.keep, "compare": c.compare} for c in result.columns],
        "records": [
            {"index": r.index, "line_start": r.line_start, "line_end": r.line_end, "cells": list(r.cells)}
            for r in result.records
        ],
        "changes": [_change_to_json(c) for c in result.changes],
        "issues": [_issue_to_json(i) for i in result.issues],
        "stats": vars(result.stats).copy(),
    }


def _change_to_json(change: Change) -> dict[str, Any]:
    if isinstance(change, CellTrimmed):
        return {"type": "cell_trimmed", "record": change.record, "column": change.column, "after": change.after}
    if isinstance(change, FormulaEscaped):
        return {"type": "formula_escaped", "record": change.record, "column": change.column, "after": change.after}
    if isinstance(change, HeaderRenamed):
        return {
            "type": "header_renamed",
            "record": change.record,
            "column": change.column,
            "after": change.after,
            "reason": change.reason.value,
        }
    if isinstance(change, RowRemoved):
        return {
            "type": "row_removed",
            "record": change.record,
            "reason": change.reason.value,
            "duplicate_of": change.duplicate_of,
        }
    raise TypeError(f"知らない変更の種類: {type(change).__name__}")


def _issue_to_json(issue: Issue) -> dict[str, Any]:
    return {
        "level": issue.level.value,
        "code": issue.code.value,
        "record": issue.record,
        "column": issue.column,
        "related_record": issue.related_record,
        "detail": issue.detail,
    }
