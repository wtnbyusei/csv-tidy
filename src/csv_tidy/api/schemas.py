"""API で受け渡す JSON の形（設計書 11.1・11.2）。

設定（options）は pydantic で値を確かめる。整形結果は行数が多くなりうるので、
pydantic の型に詰め直さず、そのまま辞書にして返す（速さのため）。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from csv_tidy.core.models import (
    CellTrimmed,
    Change,
    InputEncoding,
    Issue,
    Newline,
    OutputEncoding,
    RowRemoved,
    TidyOptions,
    TidyResult,
)


class OptionsIn(BaseModel):
    """設定（設計書 11.1）。書かれていない項目は初期値になる。知らない項目はエラーにする。"""

    model_config = ConfigDict(extra="forbid")

    input_encoding: InputEncoding | None = None
    trim: bool = True
    remove_empty: bool = True
    dedupe: bool = False
    output_encoding: OutputEncoding = OutputEncoding.UTF8
    newline: Newline = Newline.LF

    def to_core(self) -> TidyOptions:
        return TidyOptions(
            input_encoding=self.input_encoding,
            trim=self.trim,
            remove_empty=self.remove_empty,
            dedupe=self.dedupe,
            output_encoding=self.output_encoding,
            newline=self.newline,
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
