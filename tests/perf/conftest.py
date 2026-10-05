"""性能測定（NFR-01、テスト計画書 8 章）の準備。手元だけで実行する（CI では実行しない）。

    uv sync --group e2e
    uv run pytest -m perf -s

測定用のデータは scripts/gen_bench_data.py で tests/perf/data/ に作る（なければ自動で作る）。
結果は画面に表示し、tests/perf/data/result.md にも書き出す。
"""

import datetime
import importlib.util
import os
import platform
import statistics
from pathlib import Path

import pytest

from browser_fixtures import HAS_PLAYWRIGHT

if HAS_PLAYWRIGHT:
    from browser_fixtures import base_url, browser_type_launch_args, live_server  # noqa: F401
else:
    # Playwright がないときは、ブラウザでの測定だけを飛ばす
    collect_ignore = ["test_perf_browser.py"]

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data" / "bench_10mb.csv"
RESULT = DATA.parent / "result.md"

# 何回測るか（1 回目はキャッシュなどの影響を受けやすいので、複数回の中央値と最大を見る）
REPEAT = 3
# NFR-01 の基準（秒）
LIMIT_SECONDS = 5.0


@pytest.fixture(scope="session")
def bench_data() -> bytes:
    if not DATA.exists():
        spec = importlib.util.spec_from_file_location("gen_bench_data", ROOT / "scripts" / "gen_bench_data.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_bytes(module.generate(module.DEFAULT_SIZE))
    return DATA.read_bytes()


def _cpu() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "不明"


def _memory() -> str:
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return f"{total / 1024**3:.1f} GiB"
    except (ValueError, OSError, AttributeError):
        return "不明"


class Report:
    """測った時間を集め、最後に表にして書き出す。"""

    def __init__(self) -> None:
        self.rows: list[tuple[str, list[float]]] = []
        self.notes: dict[str, str] = {}

    def add(self, name: str, seconds: list[float]) -> None:
        self.rows.append((name, seconds))

    def markdown(self, size: int) -> str:
        lines = [
            f"- 測定日時: {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"- データ: {size:,} バイト（{DATA.name}）",
            f"- CPU: {_cpu()}（論理コア {os.cpu_count()}）",
            f"- メモリ: {_memory()}",
            f"- OS: {platform.platform()}",
            f"- Python: {platform.python_version()}",
            *[f"- {key}: {value}" for key, value in self.notes.items()],
            "",
            f"| 区間 | 中央値（秒） | 最大（秒） | 各回（秒） |",
            "| --- | --- | --- | --- |",
        ]
        for name, seconds in self.rows:
            each = " / ".join(f"{s:.2f}" for s in seconds)
            lines.append(f"| {name} | {statistics.median(seconds):.2f} | {max(seconds):.2f} | {each} |")
        return "\n".join(lines) + "\n"


@pytest.fixture(scope="session")
def report(bench_data):
    collected = Report()
    yield collected
    if collected.rows:
        text = collected.markdown(len(bench_data))
        RESULT.write_text(text, encoding="utf-8")
        print("\n\n性能測定の結果（NFR-01: 5 秒以内）\n" + text)
