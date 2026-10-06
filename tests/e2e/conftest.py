"""E2E テスト（テスト計画書 2 章の E）の準備。

    uv sync --group e2e
    uv run playwright install chromium   # 初回だけ
    uv run pytest -m e2e

フィクスチャは tests/browser_fixtures.py にある。
"""

from browser_fixtures import HAS_PLAYWRIGHT

# Playwright を入れていない（uv sync だけの）環境では、E2E テストを集めない
if HAS_PLAYWRIGHT:
    from browser_fixtures import base_url, browser_type_launch_args, fixture_path, live_server  # noqa: F401
else:
    collect_ignore_glob = ["test_*.py"]
