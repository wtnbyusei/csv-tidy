"""画面の用語の説明（web/help.js）の書き方の決まりを確かめる（設計書 15.6、テスト計画書 12.5）。"""

import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "src" / "csv_tidy" / "web"

# 設計書 15.6 の用語の一覧（v0.1 と v0.2）
DESIGNED_KEYS = {
    "invisible_char",
    "control_char",
    "nbsp",
    "bom",
    "cp932",
    "newline",
    "missing_cell",
    "multiline_cell",
    "column_count",
    "formula_like",
    "formula_escape",
    "duplicate",
    "compare",
    "tidy_names",
    "headerless",
    "not_output",
}


def load_help() -> dict[str, dict[str, str]]:
    """help.js の HELP を読む。中身は JSON と同じ書き方にしてある。"""
    source = (WEB / "help.js").read_text(encoding="utf-8")
    start = source.index("{", source.index("HELP ="))
    end = source.rindex("}") + 1
    return json.loads(source[start:end])


HELP = load_help()


def test_all_designed_terms_have_help():
    assert set(HELP) == DESIGNED_KEYS


@pytest.mark.parametrize("key", sorted(HELP))
def test_help_follows_writing_rules(key):
    """title・what・why がそろい、what は 40 字まで、why は 60 字までにする。"""
    entry = HELP[key]
    assert set(entry) == {"title", "what", "why"}
    assert entry["title"]
    assert 0 < len(entry["what"]) <= 40, entry["what"]
    assert 0 < len(entry["why"]) <= 60, entry["why"]


def test_used_keys_match_help():
    """画面で使っている用語のキー（helpButton("…") と data-help-slot="…"）と help.js の用語が一致する。

    使っていない説明や、説明のない「？」がないようにする。
    """
    used = set()
    for path in [*WEB.glob("*.js"), *WEB.glob("views/*.js"), WEB / "index.html"]:
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'helpButton\("([a-z_0-9]+)"\)', text))
        used |= set(re.findall(r'data-help-slot="([a-z_0-9]+)"', text))
        used |= set(re.findall(r':\s*"([a-z_0-9]+)",?\s*$', _kind_help_block(text), re.MULTILINE))
    assert used, "用語のキーが 1 つも見つからない"
    assert used == set(HELP), {"説明がない": used - set(HELP), "使っていない": set(HELP) - used}


def _kind_help_block(text: str) -> str:
    """issues.js の KIND_HELP（課題の種類 → 用語のキー）の中身。ほかのファイルでは空。"""
    match = re.search(r"const KIND_HELP = \{(.*?)\};", text, re.DOTALL)
    return match.group(1) if match else ""
