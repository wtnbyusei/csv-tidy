"""アプリの組み立て。エンドポイントと静的ファイルの配信は作業8・9で追加する。"""

from fastapi import FastAPI

import csv_tidy


def create_app() -> FastAPI:
    """FastAPI のアプリを作って返す。"""
    return FastAPI(title="csv-tidy", version=csv_tidy.__version__)
