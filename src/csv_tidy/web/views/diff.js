// 差分表示（画面設計書 4.3）。左に変更前、中央に「変更」の帯、右に変更後を、
// CSV のレコード単位で行をそろえて並べる（FR-42, FR-43）。1 ページ 100 行だけを作る。

import { PAGE_SIZE, itemAt, itemCount, lineLabel } from "../state.js";
import { el, replace } from "./dom.js";

// 取り除く空白の種類と、表示に使う印のクラス（FR-20）
const TRIM_MARKS = { " ": "ws", "　": "ws full", "\t": "ws tab", " ": "ws nbsp" };
const TRIM_NAMES = { " ": "半角スペース", "　": "全角スペース", "\t": "タブ", " ": "NBSP" };

// 値の中で印に置き換えて見せる文字: 見えない文字・制御文字（FR-18）と、セルの中の改行
const SPECIAL = /[​‌‍⁠﻿\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]|\r\n|\r|\n/g;
const SPECIAL_TEST = /[​‌‍⁠﻿\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\r\n]/;
const SPECIAL_NAMES = { "​": "ZWSP", "‌": "ZWNJ", "‍": "ZWJ", "⁠": "WJ", "﻿": "BOM", "\x7f": "DEL" };

/**
 * @param {object} handlers onMode(mode)、onMove(step)、onPage(page)
 */
export function renderDiff(container, model, view, handlers) {
  const total = itemCount(model, view.mode);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.min(view.page, pages - 1);
  const start = page * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, total);

  const left = sideTable(model, "before");
  const gutter = el("table", {}, el("tr", {}, el("th", {}, "この行で起きたこと")));
  const right = sideTable(model, "after");
  for (let i = start; i < end; i++) {
    const item = itemAt(model, view.mode, i);
    if (typeof item === "object") {
      left.append(gapRow(model, item.gap));
      gutter.append(el("tr", { className: "gap" }, el("td", {})));
      right.append(gapRow(model, item.gap));
      continue;
    }
    const focus = item === view.focus ? " focus" : "";
    left.append(beforeRow(model, item, focus));
    gutter.append(gutterRow(model, item, focus));
    right.append(afterRow(model, item, focus));
  }
  if (total === 0) {
    const none = el("tr", { className: "gap" }, el("td", { colSpan: model.width + 1 }, "変更はありません"));
    left.append(none);
    gutter.append(el("tr", { className: "gap" }, el("td", {})));
    right.append(none.cloneNode(true));
  }

  const leftSide = el("div", { className: "side" }, left);
  const rightSide = el("div", { className: "side" }, right);
  syncScroll(leftSide, rightSide);

  replace(
    container,
    toolbar(model, view, handlers),
    el(
      "div",
      { className: "diff3", dataset: { testid: "diff" } },
      el("div", { dataset: { testid: "diff-before" } }, el("h3", {}, "変更前（元のファイルの行番号）"), leftSide),
      el("div", { className: "gutter", dataset: { testid: "diff-gutter" } }, el("h3", {}, "変更"), gutter),
      el("div", { dataset: { testid: "diff-after" } }, el("h3", {}, "変更後（出力するファイルの行番号）"), rightSide),
    ),
    pages > 1 ? pageNav(page, pages, handlers) : null,
  );
}

function toolbar(model, view, handlers) {
  const radio = (mode, label) =>
    el(
      "label",
      {},
      el("input", {
        type: "radio",
        name: "diff-mode",
        value: mode,
        checked: view.mode === mode,
        on: { change: () => handlers.onMode(mode) },
      }),
      ` ${label}`,
    );
  const changes = model.changed.length;
  const position = view.cursor === null ? "―" : String(view.cursor + 1);
  return el(
    "div",
    { className: "toolbar" },
    el("div", { className: "radio" }, radio("changes", "変更箇所のみ"), radio("all", "全行")),
    el("button", { type: "button", className: "button", disabled: changes === 0, on: { click: () => handlers.onMove(-1) } }, "◀ 前の変更"),
    el("button", { type: "button", className: "button", disabled: changes === 0, on: { click: () => handlers.onMove(1) } }, "次の変更 ▶"),
    el("span", { className: "hint", dataset: { testid: "change-position" } }, `変更 ${position} / ${changes}`),
    el(
      "div",
      { className: "legend" },
      el("span", {}, el("span", { className: "swatch trimmed" }), "空白を取り除いたセル"),
      el("span", {}, el("span", { className: "swatch removed" }), "削除した行"),
      el("span", {}, el("span", { className: "swatch missing" }), "セルなし"),
      el("span", {}, el("span", { className: "ws" }), "半角 ", el("span", { className: "ws full" }), "全角の取り除いた空白"),
      el("span", {}, el("span", { className: "mark" }, "ZWSP"), " 見えない文字"),
    ),
  );
}

function pageNav(page, pages, handlers) {
  return el(
    "div",
    { className: "page-nav" },
    el("button", { type: "button", className: "button", disabled: page === 0, on: { click: () => handlers.onPage(page - 1) } }, "◀ 前のページ"),
    el("span", { dataset: { testid: "page-position" } }, `${page + 1} / ${pages} ページ`),
    el("button", { type: "button", className: "button", disabled: page === pages - 1, on: { click: () => handlers.onPage(page + 1) } }, "次のページ ▶"),
  );
}

/** 表の枠と見出しの行。見出しには列の名前（ヘッダーの値）を出す。 */
function sideTable(model, side) {
  const names = side === "before" ? model.headerBefore : model.headerAfter;
  const head = el("tr", {}, el("th", { className: "ln" }, "行"));
  for (let c = 0; c < model.width; c++) {
    const name = c < names.length ? names[c] : `（${c + 1} 列目）`;
    head.append(el("th", { title: name }, name));
  }
  const table = el("table", {}, head);
  // 列が多いときは、表を横に広げてスクロールさせる
  // 1280px の画面で 4 列が収まる幅（画面設計書 1 章）。多い列は横スクロールにする
  table.style.minWidth = `${88 + model.width * 72}px`;
  return table;
}

function gapRow(model, count) {
  return el("tr", { className: "gap" }, el("td", { colSpan: model.width + 1 }, `… 変更のない ${count} 行を省略 …`));
}

function rowClass(model, index, focus) {
  let name = model.removed.has(index) ? "removed" : "";
  if ((model.issuesByRecord.get(index) || []).some((issue) => issue.code === "duplicate")) name += " dup";
  return name + focus;
}

function beforeRow(model, index, focus) {
  const record = model.records[index];
  const trimmed = model.trimmed.get(index);
  const row = el("tr", { className: rowClass(model, index, focus), dataset: { record: String(index) } });
  row.append(el("td", { className: "ln" }, lineLabel(record)));
  for (let c = 0; c < model.width; c++) {
    if (c >= record.cells.length) {
      row.append(missingCell(record));
      continue;
    }
    const value = record.cells[c];
    const td = el("td", { title: value });
    if (trimmed && trimmed.has(c)) {
      td.className = "trimmed";
      appendTrimmed(td, value, trimmed.get(c));
    } else {
      appendValue(td, value);
    }
    row.append(td);
  }
  return row;
}

function afterRow(model, index, focus) {
  const values = model.after[index];
  const dataset = { record: String(index) };
  if (values === null) {
    return el(
      "tr",
      { className: `placeholder${focus}`, dataset },
      el("td", { className: "ln" }),
      el("td", { colSpan: model.width }, "（出力しない）"),
    );
  }
  const trimmed = model.trimmed.get(index);
  const issues = model.issuesByRecord.get(index) || [];
  const formula = new Set(issues.filter((i) => i.code === "formula_like").map((i) => i.column));
  const unencodable = new Map();
  for (const issue of issues) {
    if (issue.code !== "unencodable") continue;
    if (!unencodable.has(issue.column)) unencodable.set(issue.column, new Set());
    const code = /U\+([0-9A-F]{4,6})/.exec(issue.detail);
    if (code) unencodable.get(issue.column).add(String.fromCodePoint(parseInt(code[1], 16)));
  }

  const row = el("tr", { className: rowClass(model, index, focus), dataset });
  row.append(el("td", { className: "ln" }, String(model.outLine[index])));
  for (let c = 0; c < model.width; c++) {
    if (c >= values.length) {
      row.append(missingCell(model.records[index]));
      continue;
    }
    const classes = [];
    if (trimmed && trimmed.has(c)) classes.push("trimmed");
    if (formula.has(c)) classes.push("formula");
    if (unencodable.has(c)) classes.push("unencodable");
    const td = el("td", { className: classes.join(" "), title: values[c] });
    appendValue(td, values[c], unencodable.get(c));
    row.append(td);
  }
  return row;
}

/** セルがない（列数がヘッダーより少ない）ところ（FR-45）。中身のない空行は空欄にする。 */
function missingCell(record) {
  if (record.cells.length === 0) return el("td", {});
  return el("td", { className: "missing" }, "セルなし");
}

/** 取り除いた前後の空白を印で示し、残った値を入れる。 */
function appendTrimmed(td, before, after) {
  const lead = after === "" ? before.length : before.indexOf(after);
  const tail = after === "" ? 0 : before.length - lead - after.length;
  appendSpaces(td, before.slice(0, lead));
  appendValue(td, after);
  appendSpaces(td, before.slice(before.length - tail));
}

function appendSpaces(td, spaces) {
  for (const char of spaces) {
    td.append(el("span", { className: TRIM_MARKS[char] ?? "ws", title: TRIM_NAMES[char] ?? "空白" }));
  }
}

/** 値を文字として入れる。見えない文字・制御文字・改行は印にし、CP932 で表せない文字は枠で囲む。 */
function appendValue(td, value, unencodable) {
  if (!SPECIAL_TEST.test(value) && !(unencodable && unencodable.size)) {
    td.append(value);
    return;
  }
  let last = 0;
  for (const match of value.matchAll(SPECIAL)) {
    appendText(td, value.slice(last, match.index), unencodable);
    td.append(specialMark(match[0]));
    last = match.index + match[0].length;
  }
  appendText(td, value.slice(last), unencodable);
}

function appendText(td, text, unencodable) {
  if (!text) return;
  if (!unencodable || unencodable.size === 0) {
    td.append(text);
    return;
  }
  let buffer = "";
  for (const char of text) {
    if (unencodable.has(char)) {
      if (buffer) td.append(buffer);
      buffer = "";
      td.append(el("span", { className: "unenc-char", title: "CP932 で表せない文字" }, char));
    } else {
      buffer += char;
    }
  }
  if (buffer) td.append(buffer);
}

function specialMark(char) {
  if (char === "\n" || char === "\r" || char === "\r\n") {
    return el("span", { className: "mark nl", title: "セルの中の改行" }, "↵");
  }
  const code = `U+${char.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")}`;
  return el("span", { className: "mark", title: code }, SPECIAL_NAMES[char] ?? code);
}

/** 「変更」の帯の 1 行。その行で起きたことを矢印とバッジで書く（FR-43）。 */
function gutterRow(model, index, focus) {
  const notes = [];
  const add = (className, text) => notes.push({ className, text });

  if (index === model.result.header_record) add("note-text", "ヘッダー行");
  const removed = model.removed.get(index);
  if (removed) {
    if (removed.reason === "empty") add("badge", "削除: 空行");
    else if (removed.reason === "leading_blank") add("badge", "削除: 先頭の空行");
    else add("badge", `削除: 重複（${model.records[removed.duplicate_of].line_start} 行目と同じ）`);
  }

  const seen = new Set();
  for (const issue of model.issuesByRecord.get(index) || []) {
    if (seen.has(issue.code)) continue;
    seen.add(issue.code);
    const record = model.records[index];
    switch (issue.code) {
      case "column_count":
        add("badge warn", `列数 ${record.cells.length} / ${model.headerWidth}`);
        break;
      case "duplicate":
        add("badge dup", `重複: ${model.records[issue.related_record].line_start} 行目と同じ`);
        break;
      case "invisible_char":
        add("badge warn", "見えない文字");
        break;
      case "control_char":
        add("badge warn", "制御文字");
        break;
      case "formula_like":
        add("badge warn", "数式になる値");
        break;
      case "unencodable":
        add("badge", "CP932 で表せない");
        break;
      case "multiline_cell":
        add("badge info", "複数行のセル");
        break;
      case "leading_blank":
        add("badge info", "先頭の空行を飛ばした");
        break;
      default:
        add("badge info", issue.detail);
    }
  }

  // 帯の幅（180px）に収まらないときに大事なバッジが隠れないよう、空白の説明は最後に置く
  const trimmed = model.trimmed.get(index);
  if (trimmed) add("note-text", `空白を取り除いた（${trimmed.size} セル）`);

  const td = el("td", { title: notes.map((n) => n.text).join("／") });
  if (notes.length) td.append(el("span", { className: "arrow" }, "→"));
  for (const note of notes) td.append(el("span", { className: note.className }, note.text));
  return el("tr", { className: focus.trim(), dataset: { record: String(index) } }, td);
}

/** 左右の表の横スクロールをそろえる。 */
function syncScroll(a, b) {
  let syncing = false;
  const follow = (from, to) => () => {
    if (syncing) return;
    syncing = true;
    to.scrollLeft = from.scrollLeft;
    requestAnimationFrame(() => (syncing = false));
  };
  a.addEventListener("scroll", follow(a, b));
  b.addEventListener("scroll", follow(b, a));
}
