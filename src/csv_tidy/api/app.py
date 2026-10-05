"""アプリの組み立てと、画面（静的ファイル）の配信（設計書 11 章）。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import csv_tidy

from .errors import register_error_handlers
from .routes import router

# 画面のファイル（HTML・CSS・JavaScript）を置いた場所
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# 画面で読み込んでよいものを、このサーバーから配信したものだけに限る（NFR-07 の多重の守り）。
# 万一 CSV の値が HTML として解釈されても、外部のスクリプトやインラインのスクリプトは実行されない。
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class _StaticFiles(StaticFiles):
    """毎回、更新されていないかをサーバーに確かめさせる（古い JavaScript が残らないように）。"""

    def file_response(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app() -> FastAPI:
    """FastAPI のアプリを作って返す。"""
    app = FastAPI(title="csv-tidy", version=csv_tidy.__version__)
    app.include_router(router)
    register_error_handlers(app)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(
            WEB_DIR / "index.html",
            headers={"Content-Security-Policy": CONTENT_SECURITY_POLICY, "Cache-Control": "no-cache"},
        )

    app.mount("/static", _StaticFiles(directory=WEB_DIR), name="static")
    return app
