// 画面の部品を作る小さな道具。文字は必ず textContent（テキストノード）で入れ、
// innerHTML は使わない（設計書 12 章、NFR-07）。

import { HELP } from "../help.js";

/**
 * 要素を作る。props の className・title・hidden などはプロパティとして、
 * dataset はデータ属性として設定する。children の文字列はテキストノードになる。
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue;
    if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "on") for (const [type, fn] of Object.entries(value)) node.addEventListener(type, fn);
    else node[key] = value;
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
  }
  return node;
}

/** 中身を入れ替える。 */
export function replace(node, ...children) {
  node.replaceChildren();
  return append(node, children);
}

// ---- 用語の説明（「？」。設計書 15.6、画面設計書 11 章） ----


const HELP_POP_ID = "help-pop";
let openHelp = null; // 開いている吹き出し { button, pop }

/** 用語の横に置く「？」のボタン。押すとその場に説明の吹き出しを出す。 */
export function helpButton(key) {
  const entry = HELP[key];
  if (!entry) throw new Error(`用語の説明がありません: ${key}`);
  const button = el(
    "button",
    {
      type: "button",
      className: "help",
      title: `「${entry.title}」の説明`,
      ariaLabel: `「${entry.title}」の説明`,
      dataset: { help: key },
      on: {
        click: (event) => {
          // ラベルの中に置いてもチェックが切り替わらないようにし、外を押したときの処理にも渡さない
          event.preventDefault();
          event.stopPropagation();
          if (openHelp && openHelp.button === button) closeHelp();
          else showHelp(button, entry);
        },
      },
    },
    "?",
  );
  button.setAttribute("aria-expanded", "false");
  return button;
}

function showHelp(button, entry) {
  closeHelp();
  const pop = el(
    "div",
    { id: HELP_POP_ID, className: "help-pop", role: "dialog", ariaLabel: entry.title, on: { click: (e) => e.stopPropagation() } },
    el("strong", {}, entry.title),
    el("p", {}, entry.what),
    el("p", {}, entry.why),
  );
  document.body.append(pop);
  // 表や枠の中で切れないよう、画面に対して位置を決める（右端からはみ出さないようにする）
  const rect = button.getBoundingClientRect();
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - pop.offsetWidth - 8));
  pop.style.left = `${left}px`;
  pop.style.top = `${rect.bottom + 4}px`;
  button.setAttribute("aria-expanded", "true");
  button.setAttribute("aria-controls", HELP_POP_ID);
  openHelp = { button, pop };
}

/** 開いている吹き出しを閉じる。 */
export function closeHelp() {
  if (!openHelp) return;
  openHelp.pop.remove();
  openHelp.button.setAttribute("aria-expanded", "false");
  openHelp.button.removeAttribute("aria-controls");
  openHelp = null;
}

// Esc キー・吹き出しの外を押す・画面を動かすと閉じる
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !openHelp) return;
  const { button } = openHelp;
  closeHelp();
  button.focus();
});
document.addEventListener("click", closeHelp);
window.addEventListener("scroll", closeHelp, true);
window.addEventListener("resize", closeHelp);
