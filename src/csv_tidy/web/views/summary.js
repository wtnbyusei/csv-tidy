// 概要: 文字コード・改行コードの変換（FR-47）と件数（FR-46）。画面設計書 4.1。

import { INPUT_ENCODING_LABELS, NEWLINE_LABELS, OUTPUT_ENCODING_LABELS } from "../state.js";
import { el, replace } from "./dom.js";

export function renderSummary(container, model, options) {
  const { input, output, stats } = model.result;
  const how = input.auto_detected ? "（自動判定）" : "（指定）";
  const conv = el(
    "div",
    { className: "conv", dataset: { testid: "conversion" } },
    el("b", {}, "文字コード"),
    ` ${INPUT_ENCODING_LABELS[input.encoding]}${how} → ${OUTPUT_ENCODING_LABELS[output.encoding]}　`,
    el("b", {}, "改行"),
    ` ${NEWLINE_LABELS[input.newline]} → ${NEWLINE_LABELS[output.newline]}`,
  );

  const duplicates =
    options.dedupe
      ? count("removed", `重複の削除 ${stats.duplicates_removed} 行`, stats.duplicates_removed)
      : count(stats.duplicates_found ? "info" : "", `重複 ${stats.duplicates_found} 件（未削除）`);
  const counts = el(
    "div",
    { className: "counts", dataset: { testid: "counts" } },
    count("trimmed", `空白を取り除いた ${stats.cells_trimmed} セル`, stats.cells_trimmed),
    count("removed", `空行の削除 ${stats.empty_removed} 行`, stats.empty_removed),
    duplicates,
    count("warn", `列数の警告 ${stats.column_warnings}`, stats.column_warnings),
    count("warn", `見えない文字 ${stats.invisible_chars}`, stats.invisible_chars),
    count("warn", `制御文字 ${stats.control_chars}`, stats.control_chars),
    count("warn", `数式化の警告 ${stats.formula_warnings}`, stats.formula_warnings),
    output.encoding === "cp932"
      ? count("error", `CP932 で表せない文字 ${stats.unencodable_chars}`, stats.unencodable_chars)
      : null,
  );
  replace(container, conv, counts);
}

/** 件数の札。0 件のときは色を付けない。 */
function count(kind, text, value = 1) {
  return el("span", { className: value ? `count ${kind}` : "count" }, text);
}
