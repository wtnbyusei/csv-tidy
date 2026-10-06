# csv-tidy v0.1 受け入れテストの記録

受け入れ基準（[requirements.md](requirements.md) 6 章。第10版で 24 件）がすべて確かめられているかの点検、性能測定（NFR-01）、手動確認（[test-plan.md](test-plan.md) 7 章）の結果を記録する。開発計画（[plan.md](plan.md)）の作業10 にあたる。

- 作成日: 2026-10-06
- 用語: 分からない用語は [glossary.md](glossary.md) を参照
- 結果の凡例: ✅ 合格 / ⏳ 未実施（担当者の確認待ち） / ❌ 不合格

## 1. まとめ

| 項目 | 結果 |
| --- | --- |
| 受け入れ基準 24 件の自動テスト | 性能（21）以外の 23 件は、すべて CI で毎回実行する自動テストで確かめている。21 は手元で実行する性能測定（3 章）で確かめる。人の目が必要な部分（基準 1 の Excel）は手動確認 M1 で確かめる |
| 性能（NFR-01、基準 21） | Claude の作業環境では 3.2 秒（基準 5 秒）。**開発に使う PC での測定は未実施**（3.2 節） |
| 手動確認 | Claude が M3・M4・M7 を実施して合格（途中で見つけた表示の問題 3 件を直した）。M1・M2・M5・M6・M10 は開発者の確認待ち。M8・M9 は作業11（README）で行う |

## 2. 受け入れ基準の点検

受け入れ基準ごとに、確かめているテストを挙げる。テストのファイルは `tests/` からの場所。「E2E」は `e2e/test_web_ui.py`、「API」は `api/test_api.py`。

| # | 受け入れ基準の要点 | 確かめているテスト | 結果 |
| --- | --- | --- | --- |
| 1 | CP932 と判定され、BOM 付き UTF-8＋CRLF で出力できる。Excel で文字化けしない | `core/test_service.py::test_cp932_input_is_detected_and_exported_as_utf8_bom`（先頭の BOM と CRLF をバイト列で比べる）、`core/test_decoding.py::test_detects_cp932`、`core/test_writing.py::test_utf8_bom_crlf_starts_with_bom_and_uses_crlf`。Excel は手動確認 M1 | ✅（M1 は ⏳） |
| 2 | 前後の半角・全角の空白が取れ、内部の空白は残る | `core/test_steps.py::test_trims_half_and_full_width_spaces_but_keeps_inner_space`、性質のテスト P3 | ✅ |
| 3 | 空行とトリム後に空になる行が削除され、ヘッダーは残る | `core/test_steps.py::test_blank_rows_are_removed_regardless_of_column_count` | ✅ |
| 4 | トリム後に一致する 2 行のうち 1 行目だけが残る | `core/test_steps.py::test_duplicates_after_trim_are_removed_when_enabled`、性質のテスト P4 | ✅ |
| 5 | 列数が不正な行があっても完了し、行番号付きで警告される | `core/test_steps.py::test_rows_with_different_column_count_are_warned_and_kept`、API `test_tidy_reports_issues_and_stats`、E2E `test_main_flow_shows_summary_diff_and_issues`（「5 行目: 列数 3（ヘッダーは 4）」） | ✅ |
| 6 | 10MB を超えるファイルとデコードできないファイルが、分かりやすいエラーで拒否される | API `test_file_over_max_bytes_is_413`・`test_core_errors_become_422`、E2E `test_too_large_file_is_rejected_before_sending`・`test_manual_input_encoding_rereads_file` | ✅ |
| 7 | 3 行目のクォートの閉じ忘れと `"c"x,d` が行番号付きのエラーになる。クォート内のカンマは 1 つのセル | `core/test_parsing.py::test_unclosed_quote_reports_starting_line`・`test_character_after_closing_quote_is_error`・`test_comma_inside_quotes_is_part_of_cell`、E2E `test_errors_are_explained` | ✅ |
| 8 | `a,b` と `a,b,,` は重複ではなく、`a,b` は警告され 2 列のまま出力される | `core/test_steps.py::test_omitted_cells_and_empty_cells_are_not_duplicates`、`core/test_writing.py::test_short_rows_keep_their_length` | ✅ |
| 9 | 1000 行中 999 行目だけの変更が「変更箇所のみ」に表示され、件数に反映される | E2E `test_change_on_line_999_of_1000_is_shown`（**作業10 で件数の確認を追加**） | ✅ |
| 10 | NUL を含むファイルは拒否され、xlsx では保存し直しを案内する | `core/test_decoding.py::test_nul_character_is_rejected`・`test_xlsx_is_rejected_with_guidance`、API `test_core_errors_become_422`、E2E `test_errors_are_explained` | ✅ |
| 11 | CP932 出力で絵文字があると出力が止まり、行・列と件数が表示される | `core/test_writing.py::test_unencodable_characters_are_errors_with_position`、API `test_export_unencodable_is_422`、E2E `test_unencodable_characters_disable_download` | ✅ |
| 12 | `<script>` を含む値が実行されずに文字として表示される | E2E `test_html_in_values_is_shown_as_text`、API `test_web_files_do_not_use_inner_html` | ✅ |
| 13 | `␣=1+1` はトリム後に警告され、差分で強調される。元から `=1+1`・`-5` のものは警告しない。無害化をオフにすると値は `=1+1` のまま（第10版で変更） | `core/test_steps.py::test_cell_that_becomes_formula_like_after_trim_is_warned`・`test_originally_formula_like_cells_are_not_warned`・`test_formula_warning_is_kept_when_value_is_escaped`、E2E `test_formula_like_and_invisible_characters_are_marked_in_diff` | ✅ |
| 14 | ゼロ幅スペースだけが違う 2 行は重複にならず、ゼロ幅スペースは警告され記号で見える。C1 制御文字や DEL も警告される | `core/test_steps.py::test_rows_differing_only_by_zero_width_space_are_not_duplicates`・`test_control_and_invisible_characters_are_warned_and_kept`、E2E `test_formula_like_and_invisible_characters_are_marked_in_diff`（**作業10 で追加**） | ✅ |
| 15 | NBSP は取り除かれ、U+0085 や U+2028 は残る | `core/test_steps.py::test_trims_tab_and_nbsp`・`test_does_not_trim_other_characters`、性質のテスト P3 | ✅ |
| 16 | 文字コードを手動で変えると、その文字コードで読み直される | `core/test_service.py::test_manual_input_encoding_is_used`、API `test_manual_input_encoding`、E2E `test_manual_input_encoding_rereads_file` | ✅ |
| 17 | 各処理をオフにすると、その処理だけが行われない | `core/test_service.py::test_each_option_changes_only_its_own_processing`、API `test_options_are_applied` | ✅ |
| 18 | 10,485,760 バイトは受け付け、10,485,761 バイトはエラー | API `test_file_of_exactly_max_bytes_is_accepted`・`test_file_over_max_bytes_is_413` | ✅ |
| 19 | 0 バイト・空行だけは「データがありません」、ヘッダーだけは処理されヘッダーだけが出力される | `core/test_decoding.py::test_zero_bytes_raise_empty_data_error`、`core/test_steps.py::test_only_blank_rows_raise_empty_data_error`・`test_header_only_is_processed_and_reported`、E2E `test_empty_files_are_rejected`（**作業10 で追加**） | ✅ |
| 20 | 先頭の空行 2 行を飛ばし、3 行目がヘッダーになり「2 行を飛ばした」と表示される。出力に先頭の空行を含まない | `core/test_steps.py::test_leading_blank_rows_are_skipped_and_reported`（**作業10 で出力の確認を追加**）、E2E `test_leading_blank_rows_are_reported_and_not_exported`（**作業10 で追加**） | ✅ |
| 21 | 10MB で 5 秒以内 | 3 章の性能測定 | ⏳（開発に使う PC での測定待ち） |
| 22 | 初期状態では重複を削除せず、件数と該当行を表示する。オンにすると 2 件目以降を削除する | `core/test_steps.py::test_duplicates_are_reported_but_not_removed_by_default`・`test_duplicates_after_trim_are_removed_when_enabled`、E2E `test_main_flow_shows_summary_diff_and_issues`（「重複が 1 件あります」「重複: 2 行目と同じ」） | ✅ |
| 23 | 保存するファイル名が `顧客一覧_tidy.csv` になる | E2E `test_download_is_named_after_original_file` | ✅ |
| 24 | 初期状態で `=1+1`・`@SUM(A1)`・`＝1+1`・`+81-90-1234-5678`・`- メモ` に `'` が付き、差分と件数に表示される。ヘッダーも対象。`-5`・`+81`・`-1.5`・`-1e3` は変わらない。オフにするとどれも変わらない（第10版で追加） | `core/test_steps.py::test_values_that_can_become_formulas_need_escape`・`test_numbers_and_other_values_do_not_need_escape`・`test_escape_adds_quote_and_records_change`・`test_escape_off_keeps_values`、`core/test_service.py::test_escaped_formulas_are_exported_and_counted`、API `test_formula_escape_is_returned_as_change`、E2E `test_formulas_are_escaped_by_default_and_can_be_turned_off` | ✅ |

### 2.1 点検で見つけて補ったこと

画面に出ることを求める部分で、コアと API のテストはあるが画面のテストがないものがあった。次の E2E テストを追加した。

| 受け入れ基準 | 足りなかった部分 | 追加・変更したテスト |
| --- | --- | --- |
| 9 | 「変更の件数に反映される」 | `test_change_on_line_999_of_1000_is_shown` に件数の確認を追加 |
| 13, 14 | 「差分表示で強調される」「記号として見える」 | `test_formula_like_and_invisible_characters_are_marked_in_diff` |
| 19 | 「データがありません」というエラーの表示 | `test_empty_files_are_rejected` |
| 20 | 「2 行を飛ばした」の表示と、出力に先頭の空行を含まないこと | `test_leading_blank_rows_are_reported_and_not_exported`。コアのテストにも出力の確認を追加 |

## 3. 性能測定（NFR-01、受け入れ基準 21）

### 3.1 測り方

```sh
uv sync --group e2e
uv run playwright install chromium   # 初回だけ
uv run pytest -m perf -s
```

- データは `scripts/gen_bench_data.py` が作る 10,420,162 バイト・99,060 行×10 列の CSV（`tests/perf/data/bench_10mb.csv`）。前後の空白（20 行に 1 行）、空行（50 行に 1 行）、前の行と同じ行（100 行に 1 行）を混ぜている。なければ測定の前に自動で作る。
- 3 つの区間をそれぞれ 3 回測り、中央値（真ん中の値）と最大を出す。結果は `tests/perf/data/result.md` にも書き出す（リポジトリには入れない）。
  - ファイルを選んでから、差分の表が画面に出るまで（Playwright の Chromium）。基準 5 秒はこの区間に当てはめる
  - API（`POST /api/tidy`。JSON への変換を含む）
  - コアの整形（`TidyService.tidy`）
- 設定は初期値（自動判定、トリムと空行の削除はオン、重複の削除はオフ、出力は UTF-8・LF）。

### 3.2 結果

**Claude の作業環境（参考）**

- 測定日時: 2026-10-05
- CPU: Intel(R) Xeon(R) Processor @ 2.80GHz（論理コア 4）、メモリ 15.7 GiB、Linux
- Python 3.11.15、Chromium 141.0.7390.37（画面を表示しない形で実行）

| 区間 | 中央値（秒） | 最大（秒） | 各回（秒） |
| --- | --- | --- | --- |
| ファイルを選んでから差分が出るまで（画面） | 3.16 | 3.26 | 3.16 / 3.26 / 2.64 |
| API（POST /api/tidy。JSON への変換を含む） | 1.61 | 1.66 | 1.66 / 1.46 / 1.61 |
| コアの整形（TidyService.tidy） | 1.08 | 1.18 | 1.08 / 1.18 / 0.95 |

画面の区間の 3.2 秒のうち、おおよそ 1.6 秒がサーバー、残りのおおよそ 1.6 秒がファイルの送信・JSON の受け取り・表示用のデータ作り・表の描画。

**開発に使う PC**（受け入れ基準 21 はこちらで判定する）

⏳ 未実施。3.1 の手順で実行し、`tests/perf/data/result.md` の中身をここに貼る。

## 4. 手動確認

起動の手順は共通: `uv run csv-tidy` を実行し、ブラウザで `http://127.0.0.1:8000` を開く。確認に使うファイルは `tests/fixtures/` にある。

### 4.1 Claude が実施したもの

Playwright の Chromium（画面を表示しない形）で、画面設計の前提の幅 1280px で撮影して確かめた。画像は `docs/images/acceptance/` にある。

| # | 確認すること | 結果 | 記録 |
| --- | --- | --- | --- |
| M3 | 画面の各状態が、画面設計書の見本と大きく違わない | ✅ | 未選択 [01](images/acceptance/01-empty.png)、差分 [02](images/acceptance/02-result-diff.png)、課題 [03](images/acceptance/03-result-issues.png)、処理中 [04](images/acceptance/04-loading.png)、エラー [05](images/acceptance/05-error.png)、ダウンロードできない状態 [06](images/acceptance/06-unencodable.png)。見本からの違いは設計書 14 章の I20〜I29 に記録したもの（ヘッダー行も 1 行目に出す、など）だけ |
| M4 | 差分の色・記号・変更の帯が、画面設計書 4.3 のとおりに表示される | ✅ | `manual_check.csv` で確認した [07](images/acceptance/07-manual-check.png)。取り除いた空白（半角・全角・タブ・NBSP）、ZWSP・DEL・U+0085 の札、数式になる値の枠、セルなし、削除した行、重複の線、複数行のセル |
| M7 | 画面の文言がすべて日本語で、意味が通じる | ✅ | 01〜07 の画面の文言と、画面のプログラム（`web/app.js`）にあるすべてのエラーの見出し・確認することの文言を読んで確認した。英字は文字コードの名前（UTF-8、CP932）、改行コードの名前（LF、CRLF）、記号の札（ZWSP など）、エラーの種類（`csv_syntax` など）だけ |

**実施中に見つけて直した問題**

| # | 問題 | 対処 |
| --- | --- | --- |
| 1 | 幅 1280px の画面で、差分の左右の表の 4 列目（電話）が切れ、横にスクロールしないと見えなかった（見本では 4 列とも見える） | 1 列の最小の幅を 96px から 72px にした（設計書 14 章 I30） |
| 2 | 複数行にまたがる行の行番号「812〜813」が「812〜8…」と切れていた | 行番号の欄を 72px から 88px にした |
| 3 | 「空白を取り除いた」と「数式になる値」が同じ行にあると、変更の帯（180px）に収まらず、大事な「数式になる値」のバッジが隠れていた | 帯の中の順番を、削除・課題のバッジ → 空白の説明 にした。マウスを重ねるとすべて読める（設計書 14 章 I31） |

3 件とも、回帰テストを E2E に追加した（`test_four_columns_and_long_line_numbers_fit_at_1280px`、`test_important_badge_is_visible_in_narrow_change_column`）。テストは直した後に書いたため、直す前のコードに戻して失敗すること（2 件とも失敗）、直した後のコードで成功することを確かめた。

**気づいたこと（直していない）**

- U+2028（行区切り文字）は、FR-18 の検査の対象外なので札が付かず、画面では見えない（`manual_check.csv` の 4 行目「LS」の後ろ）。要件どおりの動きなので v0.1 では変えない。見えるようにするかは v0.2 以降の検討とする（issues.md への追加は開発者の判断を待つ）。

### 4.2 開発者に実施していただくもの

| # | 確認すること | 手順 | 合格の条件 | 結果 |
| --- | --- | --- | --- | --- |
| M1 | UTF-8（BOM 付き）＋CRLF の出力を Excel で開いて文字化けしない（受け入れ基準 1） | 1. `customers_cp932.csv` を選ぶ 2. 出力の文字コードを「UTF-8（BOM 付き・Excel 向け）」、改行コードを「CRLF（Windows）」にする 3. ダウンロードした `customers_cp932_tidy.csv` をダブルクリックして Excel で開く | 見出しが「名前・年齢・住所・電話」と読め、3 行目が「佐藤花子」（前後の空白なし）、812 行目付近の住所が 1 つのセルに 2 行で入っている | ⏳ |
| M2 | CP932 の出力を Excel で開いて文字化けしない | M1 の手順 2 で、出力の文字コードを「CP932」にする | M1 と同じ | ⏳ |
| M5 | Chrome・Edge・Firefox の最新版で主要な流れが動く（NFR-10） | 各ブラウザで: 1. `customers_utf8_bom.csv` を選ぶ 2. 「重複行を削除する」をオンにする 3. ダウンロードする | 2 で概要に「重複の削除 1 行」と出て、3 で `customers_utf8_bom_tidy.csv` が保存される | Chrome ⏳ / Edge ⏳ / Firefox ⏳ |
| M6 | ドラッグ＆ドロップで読み込める（FR-01） | エクスプローラー（Mac は Finder）から `customers_utf8_bom.csv` を、左の「ここに CSV ファイルをドロップ」の枠へ引っ張ってきて放す | 枠が青くなり、放すと結果が表示される。ブラウザがファイルを開いて画面が切り替わったりしない | ⏳ |
| M10 | `127.0.0.1` でだけ待ち受け、別の機器から接続できない（NFR-02） | 1. `uv run csv-tidy` を実行したまま、別のターミナルで Windows は `netstat -an \| findstr 8000`、Mac は `lsof -nP -iTCP:8000 -sTCP:LISTEN` を実行する 2. 同じ Wi-Fi のスマートフォンで `http://（PC の IP アドレス）:8000` を開く | 1 で待ち受け先が `127.0.0.1:8000` だけ（`0.0.0.0:8000` がない）。2 で接続できない | ⏳ |

M6 は E2E テスト（`test_drag_and_drop_reads_file`）でも確かめているが、テストはブラウザの中でドロップの操作を作り出しているだけなので、OS からの本当のドラッグは手動で確かめる。

### 4.3 作業11 で行うもの

| # | 確認すること |
| --- | --- |
| M8 | 何も入っていない PC 環境で、README の手順だけで起動できる |
| M9 | README に制限事項、スクリーンショット、設計判断へのリンクがある |
