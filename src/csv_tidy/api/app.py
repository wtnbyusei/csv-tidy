"""アプリの組み立て。画面（静的ファイル）の配信は作業9で追加する。"""

from fastapi import FastAPI

import csv_tidy

from .errors import register_error_handlers
from .routes import router


def create_app() -> FastAPI:
    """FastAPI のアプリを作って返す。"""
    app = FastAPI(title="csv-tidy", version=csv_tidy.__version__)
    app.include_router(router)
    register_error_handlers(app)
    return app
