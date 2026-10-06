"""サーバー側の処理時間を測る（テスト計画書 8 章。どこに時間がかかっているかを分けるため）。"""

import time

import pytest
from fastapi.testclient import TestClient

from csv_tidy.api.app import create_app
from csv_tidy.core.models import TidyOptions
from csv_tidy.core.service import TidyService

from .conftest import LIMIT_SECONDS, REPEAT

pytestmark = pytest.mark.perf


def measure(action) -> list[float]:
    seconds = []
    for _ in range(REPEAT):
        start = time.perf_counter()
        action()
        seconds.append(time.perf_counter() - start)
    return seconds


def test_core_tidy_time(bench_data, report):
    seconds = measure(lambda: TidyService().tidy(bench_data, TidyOptions()))
    report.add("コアの整形（TidyService.tidy）", seconds)
    assert max(seconds) < LIMIT_SECONDS


def test_api_tidy_time(bench_data, report):
    client = TestClient(create_app())

    def call():
        response = client.post("/api/tidy", files={"file": ("bench.csv", bench_data, "text/csv")})
        assert response.status_code == 200

    seconds = measure(call)
    report.add("API（POST /api/tidy。JSON への変換を含む）", seconds)
    assert max(seconds) < LIMIT_SECONDS
