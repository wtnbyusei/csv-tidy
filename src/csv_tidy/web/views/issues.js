// 課題の一覧（画面設計書 4.4）。レベルごとにまとめ、その中を課題の種類ごとに分ける。

import { ISSUES_FIRST, columnName, lineLabel } from "../state.js";
import { el, replace } from "./dom.js";

const LEVELS = [
  { level: "error", title: "エラー（ダウンロードできません）" },
  { level: "warning", title: "警告" },
  { level: "info", title: "情報" },
];

/** 課題の種類の見出し。並び順もこの順にする。 */
const KINDS = {
  unencodable: "CP932 で表せない文字",
  column_count: "列数がヘッダーと違う行",
  invisible_char: "見えない文字",
  control_char: "制御文字",
  formula_like: "数式として扱われるおそれのある値",
  duplicate: "重複している行",
  multiline_cell: "複数行にまたがるセル",
  leading_blank: "先頭の空行",
  no_data_rows: "データ行がない",
};

/** 「さらに表示」で 1 回に増やす件数。 */
const MORE_STEP = 100;

/**
 * @param {object} handlers onJump(record): 差分の行へ移動する。onMore(code): 表示する件数を増やす。
 */
export function renderIssues(container, model, view, options, handlers) {
  const issues = model.result.issues;
  if (issues.length === 0) {
    replace(container, el("p", { className: "hint" }, "課題はありません。"));
    return;
  }

  const groups = [];
  for (const { level, title } of LEVELS) {
    const ofLevel = issues.filter((issue) => issue.level === level);
    if (ofLevel.length === 0) continue;

    const byCode = new Map(Object.keys(KINDS).map((code) => [code, []]));
    for (const issue of ofLevel) {
      if (!byCode.has(issue.code)) byCode.set(issue.code, []);
      byCode.get(issue.code).push(issue);
    }

    const group = el(
      "details",
      { className: `issue-group ${level}`, open: true, dataset: { level } },
      el("summary", {}, title, el("span", { className: `count ${level === "warning" ? "warn" : level}` }, `${ofLevel.length} 件`)),
    );
    for (const [code, list] of byCode) {
      if (list.length === 0) continue;
      group.append(...renderKind(model, view, options, handlers, code, list));
    }
    if (level === "error") {
      group.append(
        el("div", { className: "remedy" }, "対処: 元のデータを直すか、出力の文字コードを UTF-8 にしてください。"),
      );
    }
    groups.push(group);
  }
  replace(container, groups);
}

function renderKind(model, view, options, handlers, code, list) {
  let heading = `${KINDS[code] ?? code}（${list.length} 件）`;
  if (code === "duplicate" && !options.dedupe) heading += "・重複行の削除はオフです";

  const shown = view.shown[code] ?? ISSUES_FIRST;
  const items = list.slice(0, shown).map((issue) => el("li", {}, describe(model, issue, handlers)));
  const nodes = [el("div", { className: "issue-head issue-kind" }, heading), el("ul", { dataset: { code } }, items)];

  const rest = list.length - shown;
  if (rest > 0) {
    nodes.push(
      el(
        "div",
        { className: "issue-more" },
        el(
          "button",
          { type: "button", className: "button", on: { click: () => handlers.onMore(code, shown + MORE_STEP) } },
          `さらに表示（残り ${rest} 件）`,
        ),
      ),
    );
  }
  return nodes;
}

/** 1 件の課題。行がある課題は、押すと差分の行へ移動する。 */
function describe(model, issue, handlers) {
  if (issue.record === null) return issue.detail;
  const record = model.records[issue.record];
  let place = `${lineLabel(record)} 行目`;
  if (issue.column !== null) place += `・${columnName(model, issue.column)}の列`;
  const text = issue.code === "multiline_cell" ? place : `${place}: ${issue.detail}`;
  return el(
    "button",
    {
      type: "button",
      className: "link",
      dataset: { record: String(issue.record) },
      on: { click: () => handlers.onJump(issue.record) },
    },
    `${text} → 差分で見る`,
  );
}
