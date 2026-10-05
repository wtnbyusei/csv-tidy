"""エンドポイント（設計書 11 章）。サーバーは状態を持たない（NFR-08）。"""

from typing import Annotated

import orjson
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from csv_tidy.core.models import MAX_BYTES, OutputEncoding, TidyOptions
from csv_tidy.core.service import TidyService

from .errors import ApiError
from .schemas import OptionsIn, result_to_json

router = APIRouter(prefix="/api")
service = TidyService()

# 出力のバイト列の文字コードを、ブラウザに伝えるための名前
_CHARSETS = {
    OutputEncoding.UTF8: "utf-8",
    OutputEncoding.UTF8_BOM: "utf-8",
    OutputEncoding.CP932: "windows-31j",
}

FileField = Annotated[UploadFile, File(description="CSV ファイル")]
OptionsField = Annotated[str, Form(description="設定の JSON 文字列（設計書 11.1）")]


@router.post("/tidy")
async def tidy(file: FileField, options: OptionsField = "{}") -> Response:
    """整形結果を JSON で返す（画面の表示用）。

    10MB のファイルでは応答が 17MiB ほどになる。標準の json では変換に 0.7 秒ほど
    かかるため、orjson で変換する（0.02 秒ほど。設計書 14 章 I16）。
    """
    data = await _read_limited(file)
    result = service.tidy(data, _parse_options(options))
    return Response(content=orjson.dumps(result_to_json(result, size=len(data))), media_type="application/json")


@router.post("/export")
async def export(file: FileField, options: OptionsField = "{}") -> Response:
    """整形後の CSV を返す（ダウンロード用）。保存するファイル名は画面側で付ける（設計書 D7）。"""
    data = await _read_limited(file)
    parsed = _parse_options(options)
    content = service.export(data, parsed)
    return Response(content=content, media_type=f"text/csv; charset={_CHARSETS[parsed.output_encoding]}")


async def _read_limited(file: UploadFile) -> bytes:
    """上限（FR-02）を 1 バイトでも超えたら 413 にする。上限より 1 バイトだけ多く読んで判定する。"""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError(
            413,
            "file_too_large",
            f"ファイルが大きすぎます。{MAX_BYTES:,} バイト（10MB）以下のファイルを選んでください。",
            limit=MAX_BYTES,
        )
    return data


def _parse_options(raw: str) -> TidyOptions:
    try:
        return OptionsIn.model_validate_json(raw).to_core()
    except ValidationError as error:
        fields = sorted({".".join(str(p) for p in e["loc"]) or "(全体)" for e in error.errors()})
        raise ApiError(
            422,
            "invalid_options",
            "設定の値が正しくありません。",
            fields=fields,
        ) from None
