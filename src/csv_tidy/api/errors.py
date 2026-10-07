"""例外を HTTP のエラー応答に変える（設計書 11.3）。

形は {"error": {"code": ..., "message": 日本語の説明, ...追加の項目}} にそろえる。
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from csv_tidy.core.errors import (
    CsvSyntaxError,
    DecodeError,
    InvalidColumnsError,
    NotCsvError,
    TidyError,
    UnencodableError,
)


class ApiError(Exception):
    """API の層で見つけた問題（サイズ超過、設定の誤り）。"""

    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def error_body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


def _tidy_error_extra(error: TidyError) -> dict[str, Any]:
    if isinstance(error, CsvSyntaxError):
        return {"line": error.line}
    if isinstance(error, NotCsvError):
        return {"looks_like_xlsx": error.looks_like_xlsx}
    if isinstance(error, DecodeError):
        return {"encoding": error.encoding}
    if isinstance(error, InvalidColumnsError):
        return {"fields": ["columns"], "width": error.width}
    if isinstance(error, UnencodableError):
        return {"count": error.count}
    return {}


async def _handle_tidy_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, TidyError)
    return JSONResponse(status_code=422, content=error_body(error.code, error.message, **_tidy_error_extra(error)))


async def _handle_api_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ApiError)
    return JSONResponse(status_code=error.status, content=error_body(error.code, error.message, **error.extra))


async def _handle_validation_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in error.errors()})
    return JSONResponse(
        status_code=422,
        content=error_body(
            "invalid_request",
            "送られてきた内容が足りないか、形が正しくありません。",
            fields=fields,
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(TidyError, _handle_tidy_error)
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
