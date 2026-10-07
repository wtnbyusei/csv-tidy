// 列の一覧（v0.2、画面設計書 7.1 の B改）。出力するか・列名・重複の判定に使うかを列ごとに設定し、
// つまみで順番を入れ替える。一覧そのものが設定 columns の最終形を表す（画面設計書 7.2）。

import { el, helpButton, replace } from "./dom.js";

/**
 * @param {HTMLElement} container 一覧を入れる要素
 * @param {Array} entries 一覧の行（{ source, name, keep, compare, original, headerless }）。出力の順番に並ぶ
 * @param {object} handlers onKeep(i, keep)、onCompare(i, compare)、onRename(i, name)、onMove(from, to)
 */
export function renderColumns(container, entries, handlers) {
  const head = el(
    "div",
    { className: "col-head" },
    el("span", {}),
    el("span", { className: "c" }, "出力", helpButton("not_output")),
    el("span", {}, "列名", helpButton("headerless")),
    el("span", { className: "c" }, "重複の判定", helpButton("compare")),
  );
  const rows = entries.map((entry, i) => columnRow(entry, i, entries.length, handlers));
  replace(container, head, ...rows);
}

/** 列の表示名。ヘッダーにない列は「N 列目（ヘッダーなし）」、空の列名は「N 列目（空）」。 */
export function columnLabel(entry) {
  if (entry.headerless) return `${entry.source + 1} 列目（ヘッダーなし）`;
  if (entry.original === "") return `${entry.source + 1} 列目（空）`;
  return entry.original.replace(/\r\n|\r|\n/g, "↵");
}

function columnRow(entry, i, count, handlers) {
  const label = columnLabel(entry);
  const value = entry.name ?? entry.original;
  const row = el("div", {
    className: `col-row${entry.keep ? "" : " off"}`,
    dataset: { source: String(entry.source), testid: "column-row" },
  });

  // つまみ: ドラッグで移動する。キーボードでは ↑↓ キーで 1 つずつ移動する。
  // Firefox は button 要素をドラッグできないので、フォーカスできる span にする
  const handle = el(
    "span",
    {
      className: "handle",
      tabIndex: 0,
      role: "button",
      draggable: true,
      title: "ドラッグで順番を入れ替え（↑↓ キーでも移動）",
      ariaLabel: `${label} の順番を入れ替える（↑↓ キー）`,
      on: {
        keydown: (event) => {
          const to = event.key === "ArrowUp" ? i - 1 : event.key === "ArrowDown" ? i + 1 : null;
          if (to === null) return;
          event.preventDefault();
          if (to >= 0 && to < count) handlers.onMove(i, to);
        },
        dragstart: (event) => {
          event.dataTransfer.setData("text/plain", String(i));
          event.dataTransfer.effectAllowed = "move";
          row.classList.add("dragging");
        },
        dragend: () => row.classList.remove("dragging"),
      },
    },
    "⋮⋮",
  );
  row.addEventListener("dragover", (event) => {
    event.preventDefault();
    row.classList.add("drop");
  });
  row.addEventListener("dragleave", () => row.classList.remove("drop"));
  row.addEventListener("drop", (event) => {
    event.preventDefault();
    row.classList.remove("drop");
    const from = Number(event.dataTransfer.getData("text/plain"));
    if (Number.isInteger(from) && from !== i) handlers.onMove(from, i);
  });

  const keep = el("input", {
    type: "checkbox",
    className: "box",
    checked: entry.keep,
    ariaLabel: `${label} を出力する`,
    on: { change: (event) => handlers.onKeep(i, event.target.checked) },
  });

  const name = el("input", {
    type: "text",
    className: `name${entry.headerless || entry.original === "" ? " empty" : ""}`,
    value,
    placeholder: label,
    title: value || label,
    ariaLabel: `${label} の出力する列名`,
    on: {
      change: (event) => handlers.onRename(i, event.target.value),
      keydown: (event) => {
        if (event.key === "Enter") event.target.blur();
      },
    },
  });
  const renamed = entry.name !== null && entry.name !== entry.original;
  const nameCell = el(
    "span",
    { className: "name-cell" },
    name,
    renamed ? el("small", { className: "orig", title: `元の名前: ${label}` }, `← ${label}`) : null,
  );

  const compare = el(
    "button",
    {
      type: "button",
      className: `chip${entry.compare ? " on" : ""}`,
      title: "この列を重複の判定に使う（押すと切り替え）",
      ariaLabel: `${label} を重複の判定に使う`,
      on: { click: () => handlers.onCompare(i, !entry.compare) },
    },
    entry.compare ? "比べる" : "比べない",
  );
  compare.setAttribute("aria-pressed", String(entry.compare));

  row.append(handle, keep, nameCell, compare);
  return row;
}
