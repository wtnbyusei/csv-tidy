"""API の結合テスト（設計書 11 章、FR-02・12・16・17、NFR-08、受け入れ基準 1・5・6・7・10・11・16・18・19）。"""

import json

import pytest
from fastapi.testclient import TestClient

from csv_tidy.api.app import WEB_DIR, create_app
from csv_tidy.core.models import MAX_BYTES
from helpers import make_csv

client = TestClient(create_app())


def post(path, data, options=None, filename="data.csv"):
    form = {} if options is None else {"options": json.dumps(options)}
    return client.post(path, files={"file": (filename, data, "text/csv")}, data=form)


SAMPLE = make_csv(
    [
        ["名前", "年齢", "住所"],
        ["  山田　", "30", "東京都"],
        ["", "", ""],
        ["鈴木", "41"],
        ["山田", "30", "東京都"],
    ],
    encoding="cp932",
    newline="\r\n",
)


# --- POST /api/tidy ---------------------------------------------------------------


def test_tidy_returns_result_in_designed_shape():
    response = post("/api/tidy", SAMPLE)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"input", "output", "header_record", "width", "columns", "records", "changes", "issues", "stats"}
    assert body["input"] == {"encoding": "cp932", "auto_detected": True, "newline": "crlf", "size": len(SAMPLE)}
    assert body["output"] == {"encoding": "utf-8", "newline": "lf", "exportable": True}
    assert body["header_record"] == 0
    assert body["records"][1] == {"index": 1, "line_start": 2, "line_end": 2, "cells": ["  山田　", "30", "東京都"]}
    assert body["changes"] == [
        {"type": "cell_trimmed", "record": 1, "column": 0, "after": "山田"},
        {"type": "row_removed", "record": 2, "reason": "empty", "duplicate_of": None},
    ]


def test_tidy_reports_issues_and_stats():
    """受け入れ基準 5・22: 列数の警告と、削除していない重複の情報が返る。"""
    body = post("/api/tidy", SAMPLE).json()
    assert {(i["level"], i["code"], i["record"]) for i in body["issues"]} == {
        ("warning", "column_count", 3),
        ("info", "duplicate", 4),
    }
    duplicate = next(i for i in body["issues"] if i["code"] == "duplicate")
    assert duplicate["related_record"] == 1
    assert body["stats"]["cells_trimmed"] == 1
    assert body["stats"]["empty_removed"] == 1
    assert body["stats"]["duplicates_found"] == 1


def test_options_are_applied():
    """受け入れ基準 17: 設定を変えると結果が変わる。"""
    body = post("/api/tidy", SAMPLE, {"trim": False, "remove_empty": False, "dedupe": True}).json()
    assert [c["type"] for c in body["changes"]] == []
    # トリムしないと「  山田　」と「山田」は別の値なので、重複にはならない
    assert body["stats"]["duplicates_removed"] == 0


def test_formula_escape_is_returned_as_change():
    """FR-49: 無害化は変更として返し、設定でオフにできる。"""
    data = make_csv([["名前"], ["=1+1"]])
    body = post("/api/tidy", data).json()
    assert body["changes"] == [{"type": "formula_escaped", "record": 1, "column": 0, "after": "'=1+1"}]
    assert body["stats"]["formulas_escaped"] == 1
    body = post("/api/tidy", data, {"escape_formulas": False}).json()
    assert body["changes"] == []


def test_manual_input_encoding():
    """受け入れ基準 16: 文字コードを指定すると、その文字コードで読み直す。"""
    body = post("/api/tidy", b"a,b\n", {"input_encoding": "cp932"}).json()
    assert body["input"]["encoding"] == "cp932"
    assert body["input"]["auto_detected"] is False


def test_wrong_manual_encoding_is_decode_failed():
    response = post("/api/tidy", SAMPLE, {"input_encoding": "utf-8"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "decode_failed"
    assert response.json()["error"]["encoding"] == "utf-8"


def test_unencodable_is_reported_in_tidy():
    """受け入れ基準 11: CP932 出力で絵文字があると、出力できない状態と件数が返る。"""
    body = post("/api/tidy", make_csv([["名前"], ["山田😀"]]), {"output_encoding": "cp932"}).json()
    assert body["output"]["exportable"] is False
    assert body["stats"]["unencodable_chars"] == 1
    assert body["issues"][0]["level"] == "error"
    assert body["issues"][0]["code"] == "unencodable"


# --- POST /api/export -------------------------------------------------------------


def test_export_returns_csv_bytes():
    """受け入れ基準 1: BOM 付き UTF-8・CRLF で出力する。"""
    response = post("/api/export", SAMPLE, {"output_encoding": "utf-8-bom", "newline": "crlf"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.content == b"\xef\xbb\xbf" + "名前,年齢,住所\r\n山田,30,東京都\r\n鈴木,41\r\n山田,30,東京都\r\n".encode()


def test_export_cp932():
    response = post("/api/export", make_csv([["名前"], ["髙橋"]]), {"output_encoding": "cp932"})
    assert response.headers["content-type"] == "text/csv; charset=windows-31j"
    assert response.content == "名前\n髙橋\n".encode("cp932")


def test_export_unencodable_is_422():
    """受け入れ基準 11: 出力できないときは 422 と件数を返す。"""
    response = post("/api/export", make_csv([["名前"], ["😀"], ["—"]]), {"output_encoding": "cp932"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "unencodable"
    assert error["count"] == 2
    assert "CP932" in error["message"]


def test_export_does_not_set_file_name():
    """設計書 D7: 保存するファイル名は画面側で付ける。"""
    response = post("/api/export", SAMPLE)
    assert "content-disposition" not in response.headers


# --- ファイルサイズ（FR-02） ------------------------------------------------------


def _file_of_size(size):
    header = b"h\n"
    return header + b"x" * (size - len(header))


@pytest.mark.parametrize("path", ["/api/tidy", "/api/export"])
def test_file_of_exactly_max_bytes_is_accepted(path):
    """受け入れ基準 18: 10,485,760 バイトちょうどは受け付ける。"""
    data = _file_of_size(MAX_BYTES)
    assert len(data) == 10_485_760
    assert post(path, data).status_code == 200


@pytest.mark.parametrize("path", ["/api/tidy", "/api/export"])
def test_file_over_max_bytes_is_413(path):
    """受け入れ基準 6・18: 10,485,761 バイトは 413。"""
    response = post(path, _file_of_size(MAX_BYTES + 1))
    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "file_too_large"
    assert error["limit"] == MAX_BYTES


# --- コアのエラー（設計書 11.3） ---------------------------------------------------


@pytest.mark.parametrize(
    ("data", "code", "extra"),
    [
        (b"", "empty_data", {}),  # 受け入れ基準 19
        (b"\n,,\n", "empty_data", {}),  # 受け入れ基準 19
        (b"PK\x03\x04\x00\x00", "not_csv", {"looks_like_xlsx": True}),  # 受け入れ基準 10
        (b"a,\x00b\n", "not_csv", {"looks_like_xlsx": False}),  # 受け入れ基準 10
        (b"a,b\n\x81\x20\n", "decode_failed", {"encoding": None}),  # 受け入れ基準 6
        (b'h1,h2\na,b\n"c,d\ne,f\n', "csv_syntax", {"line": 3}),  # 受け入れ基準 7
    ],
)
def test_core_errors_become_422(data, code, extra):
    response = post("/api/tidy", data)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]  # 画面に出す日本語の説明がある
    for key, value in extra.items():
        assert error[key] == value


# --- 送られてきた内容の誤り -------------------------------------------------------


@pytest.mark.parametrize(
    ("options", "field"),
    [
        ('{"trim": "x"}', "trim"),
        ('{"output_encoding": "utf-16"}', "output_encoding"),
        ('{"input_encoding": "latin-1"}', "input_encoding"),
        ('{"newline": "cr"}', "newline"),
        ('{"unknown": true}', "unknown"),
    ],
)
def test_invalid_options_are_422(options, field):
    response = client.post("/api/tidy", files={"file": ("a.csv", b"a\n")}, data={"options": options})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_options"
    assert field in error["fields"]


def test_options_that_are_not_json_are_422():
    response = client.post("/api/tidy", files={"file": ("a.csv", b"a\n")}, data={"options": "not json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_options"


def test_missing_file_is_422():
    response = client.post("/api/tidy", data={"options": "{}"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert "file" in error["fields"]


def test_options_default_when_omitted():
    """設定を送らないときは初期値（重複の削除はオフ）で処理する。"""
    body = post("/api/tidy", SAMPLE).json()
    assert body["stats"]["duplicates_removed"] == 0


# --- 状態を持たないこと（NFR-08） --------------------------------------------------


def test_each_request_is_independent():
    """NFR-08: 同じファイルを設定だけ変えて 2 回送ると、それぞれ独立した結果が返る。"""
    first = post("/api/tidy", SAMPLE, {"dedupe": True}).json()
    second = post("/api/tidy", SAMPLE).json()
    third = post("/api/tidy", SAMPLE, {"dedupe": True}).json()
    assert first["stats"]["duplicates_removed"] == 1
    assert second["stats"]["duplicates_removed"] == 0
    assert first == third


# --- 画面の配信（設計書 11 章の GET /・GET /static/...） ----------------------------------


def test_index_returns_page_with_content_security_policy():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<script type="module" src="/static/app.js">' in response.text
    # 画面で読み込めるのは、このサーバーから配信したものだけ（NFR-07 の多重の守り）
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy
    assert "default-src 'self'" in policy


@pytest.mark.parametrize(
    "path",
    ["app.js", "api.js", "state.js", "views/dom.js", "views/summary.js", "views/issues.js", "views/diff.js"],
)
def test_static_scripts_are_served_as_javascript(path):
    # ES モジュールは、Content-Type が JavaScript でないとブラウザが実行しない
    response = client.get(f"/static/{path}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["cache-control"] == "no-cache"


def test_static_css_is_served():
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_web_files_do_not_use_inner_html():
    # 値は textContent（テキストノード）で入れ、HTML として解釈させない（設計書 12 章、NFR-07）
    for path in WEB_DIR.rglob("*.js"):
        source = path.read_text(encoding="utf-8")
        for word in (".innerHTML", ".outerHTML", ".insertAdjacentHTML", "document.write"):
            assert word not in source, f"{path.name} で {word} を使っている"


# --- v0.2 の列の操作（設計書 15 章） --------------------------------------------------

COLUMNS_SAMPLE = make_csv([["ID", "氏名", ""], ["1", "山田", "x", "追加"], ["2", "山田", "x"]])


def test_tidy_returns_width_columns_and_header_renamed():
    body = post("/api/tidy", COLUMNS_SAMPLE).json()
    assert body["width"] == 4
    assert body["columns"] == [{"source": s, "keep": True, "compare": True} for s in range(4)]
    renamed = [c for c in body["changes"] if c["type"] == "header_renamed"]
    assert renamed == [
        {"type": "header_renamed", "record": 0, "column": 2, "after": "列3", "reason": "tidied"},
        {"type": "header_renamed", "record": 0, "column": 3, "after": "列4", "reason": "tidied"},
    ]
    assert body["stats"]["header_names_tidied"] == 2


def test_columns_option_is_applied_and_compare_defaults_to_keep():
    """`compare` を書かないと `keep` と同じになる（設計書 15.1）。ID を出力せず比べないと重複になる。"""
    columns = [
        {"source": 1, "name": "名前"},
        {"source": 0, "keep": False},
        {"source": 2, "keep": True},
        {"source": 3, "keep": False},
    ]
    body = post("/api/tidy", COLUMNS_SAMPLE, {"columns": columns, "tidy_names": False}).json()
    assert body["columns"] == [
        {"source": 1, "keep": True, "compare": True},
        {"source": 0, "keep": False, "compare": False},
        {"source": 2, "keep": True, "compare": True},
        {"source": 3, "keep": False, "compare": False},
    ]
    assert [i["record"] for i in body["issues"] if i["code"] == "duplicate"] == [2]
    assert [i["column"] for i in body["issues"] if i["code"] == "header_name"] == [2]
    exported = post("/api/export", COLUMNS_SAMPLE, {"columns": columns, "tidy_names": False, "dedupe": True})
    assert exported.content == "名前,\n山田,x\n".encode()


@pytest.mark.parametrize("sources", [[0, 1, 2], [0, 1, 2, 2], [0, 1, 2, 4]])
@pytest.mark.parametrize("path", ["/api/tidy", "/api/export"])
def test_columns_that_are_not_a_permutation_are_422(path, sources):
    """設計書 V2: 列の並べ替え（抜け・重なり・範囲外がない）でなければ 422。"""
    response = post(path, COLUMNS_SAMPLE, {"columns": [{"source": s} for s in sources]})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_options"
    assert error["fields"] == ["columns"]
    assert error["width"] == 4


@pytest.mark.parametrize(
    "column",
    [{"source": -1}, {"source": 0, "unknown": 1}, {"name": "a"}, {"source": 0, "keep": "maybe"}],
)
def test_malformed_column_is_422(column):
    response = post("/api/tidy", b"a\n", {"columns": [column]})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_options"
    assert any(field.startswith("columns") for field in error["fields"])
