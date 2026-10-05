"""起動の入口を確かめる（NFR-02）。"""

from fastapi import FastAPI

import csv_tidy.__main__ as entry
from csv_tidy.api.app import create_app


def test_server_listens_only_on_localhost(monkeypatch):
    called = {}

    def fake_run(app, **kwargs):
        called["app"] = app
        called.update(kwargs)

    monkeypatch.setattr(entry.uvicorn, "run", fake_run)
    entry.main()

    assert called["host"] == "127.0.0.1"
    assert isinstance(called["app"], FastAPI)


def test_create_app_returns_fastapi_app():
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "csv-tidy"
