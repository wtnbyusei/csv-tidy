// 画面の部品を作る小さな道具。文字は必ず textContent（テキストノード）で入れ、
// innerHTML は使わない（設計書 12 章、NFR-07）。

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
