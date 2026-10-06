// 画面の状態（ファイル・設定・結果・表示の位置）と、整形結果から表示用のデータを作る処理。

/** 上限のバイト数（FR-02）。サーバーの MAX_BYTES と同じ値。 */
export const MAX_BYTES = 10 * 1024 * 1024;

/** 「変更箇所のみ」で、変更のある行の前後に表示する行数（要件定義書 7.1）。 */
export const CONTEXT_ROWS = 3;

/** 1 ページに表示する行数（要件定義書 7.1）。 */
export const PAGE_SIZE = 100;

/** 課題の一覧で、種類ごとに最初に表示する件数（FR-16）。 */
export const ISSUES_FIRST = 20;

/** 初期の設定（設計書 11.1）。 */
export function defaultOptions() {
  return {
    input_encoding: null,
    trim: true,
    remove_empty: true,
    dedupe: false,
    escape_formulas: true,
    output_encoding: "utf-8",
    newline: "lf",
  };
}

/**
 * 画面の状態。status は設計書 10.2 の状態
 * （"empty" 未選択、"loading" 処理中、"ready" 結果の表示中、"failed" エラーの表示中）。
 */
export const state = {
  status: "empty",
  file: null,
  options: defaultOptions(),
  result: null,
  resultOptions: null, // result を求めたときの設定（処理中に設定が変わっても、表示とダウンロードは result に合わせる）
  model: null,
  error: null,
  exporting: false,
  exportError: null,
  view: newView(),
};

export function newView() {
  return {
    tab: "diff", // "diff" または "issues"
    mode: "changes", // "changes"（変更箇所のみ）または "all"（全行）
    page: 0,
    focus: null, // 強調している行（レコードの番号）
    cursor: null, // 「変更 k / N」の k - 1
    shown: {}, // 課題の種類ごとに表示している件数
  };
}

// ---- 表示に使う名前 ----

export const INPUT_ENCODING_LABELS = { "utf-8-sig": "UTF-8（BOM 付き）", "utf-8": "UTF-8", cp932: "CP932" };
export const OUTPUT_ENCODING_LABELS = { "utf-8": "UTF-8", "utf-8-bom": "UTF-8（BOM 付き）", cp932: "CP932" };
export const NEWLINE_LABELS = { lf: "LF", crlf: "CRLF", cr: "CR", mixed: "混在", none: "改行なし" };

/** 保存するファイルの名前（FR-50）。最後の「.」より後ろを拡張子として除き、_tidy.csv を付ける。 */
export function downloadName(fileName) {
  const dot = fileName.lastIndexOf(".");
  const stem = dot > 0 ? fileName.slice(0, dot) : fileName;
  return `${stem}_tidy.csv`;
}

export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ---- 整形結果から表示用のデータを作る ----

/**
 * 変更前の値に変更の記録を当てはめて、変更後の値を作る（設計書 D2・I12）。
 * サーバーの writing.replay_changes() と同じ手順にする。削除した行は null にする。
 */
export function replayChanges(result) {
  const after = result.records.map((record) => record.cells.slice());
  for (const change of result.changes) {
    // 削除以外の変更（空白を取り除いた、数式を無害化した）は、記録された変更後の値に差し替える
    if (change.type === "row_removed") after[change.record] = null;
    else after[change.record][change.column] = change.after;
  }
  return after;
}

const NEWLINES = /\r\n|\r|\n/g;

/**
 * 表示に使うデータをまとめて作る。records の index は 0 から順に並んでいる（parsing.py）。
 * 大きなファイル（約 10 万行）でも 1 回の走査で済むようにする。
 */
export function buildModel(result) {
  const records = result.records;
  const count = records.length;
  const after = replayChanges(result);

  const removed = new Map(); // レコード → 削除の記録
  const trimmed = new Map(); // レコード → Map（空白を取り除いた列 → 取り除いた後の値）
  const escaped = new Map(); // レコード → Map（数式を無害化した列 → 無害化した後の値）（FR-49）
  for (const change of result.changes) {
    if (change.type === "row_removed") {
      removed.set(change.record, change);
      continue;
    }
    const byRecord = change.type === "formula_escaped" ? escaped : trimmed;
    let columns = byRecord.get(change.record);
    if (!columns) byRecord.set(change.record, (columns = new Map()));
    columns.set(change.column, change.after);
  }

  const issuesByRecord = new Map();
  for (const issue of result.issues) {
    if (issue.record === null) continue;
    let list = issuesByRecord.get(issue.record);
    if (!list) issuesByRecord.set(issue.record, (list = []));
    list.push(issue);
  }

  // 出力するファイルでの行番号。セルの中の改行はそのまま出力されるので、その分だけ進める
  const outLine = new Array(count).fill(null);
  let line = 1;
  let width = 0;
  for (let i = 0; i < count; i++) {
    const record = records[i];
    if (record.cells.length > width) width = record.cells.length;
    if (after[i] === null) continue;
    outLine[i] = line;
    line += 1;
    if (record.line_end > record.line_start) {
      for (const value of after[i]) line += (value.match(NEWLINES) || []).length;
    }
  }

  // 変更か課題のある行（「変更 k / N」の対象）
  const changed = [];
  for (let i = 0; i < count; i++) {
    if (removed.has(i) || trimmed.has(i) || escaped.has(i) || issuesByRecord.has(i)) changed.push(i);
  }

  const header = records[result.header_record];
  return {
    result,
    records,
    after,
    removed,
    trimmed,
    escaped,
    issuesByRecord,
    outLine,
    changed,
    width,
    headerWidth: header.cells.length,
    headerBefore: header.cells,
    headerAfter: after[result.header_record],
    changesView: changesOnlyItems(changed, count),
  };
}

/**
 * 「変更箇所のみ」に並べる項目。行（レコードの番号）と、省略をまとめた { gap: 件数 } の配列。
 * あわせて、レコードの番号から項目の位置を引く Map を返す。
 */
function changesOnlyItems(changed, count) {
  const items = [];
  const position = new Map();
  let next = 0; // まだ並べていない最初の行
  for (const record of changed) {
    const start = Math.max(record - CONTEXT_ROWS, next);
    const end = Math.min(record + CONTEXT_ROWS, count - 1);
    if (start > next) items.push({ gap: start - next });
    for (let i = start; i <= end; i++) {
      position.set(i, items.length);
      items.push(i);
    }
    next = Math.max(next, end + 1);
  }
  if (next < count) items.push({ gap: count - next });
  return { items, position };
}

/** 今の表示（変更箇所のみ・全行）の項目の数。 */
export function itemCount(model, mode) {
  return mode === "all" ? model.records.length : model.changesView.items.length;
}

/** 今の表示の i 番目の項目。 */
export function itemAt(model, mode, i) {
  return mode === "all" ? i : model.changesView.items[i];
}

/** レコードが今の表示の何ページ目にあるか。表示に含まれないときは null。 */
export function pageOf(model, mode, record) {
  const position = mode === "all" ? record : model.changesView.position.get(record);
  return position === undefined ? null : Math.floor(position / PAGE_SIZE);
}

/** 変更のある行の一覧の中で、record 以上の最初の位置（二分探索）。 */
export function changeIndexAtOrAfter(model, record) {
  let low = 0;
  let high = model.changed.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (model.changed[mid] < record) low = mid + 1;
    else high = mid;
  }
  return low;
}

/** 元のファイルでの行番号の表示（複数行にまたがるときは「812〜813」）。 */
export function lineLabel(record) {
  return record.line_end > record.line_start ? `${record.line_start}〜${record.line_end}` : String(record.line_start);
}

/** 列の名前（ヘッダーの値）。空やヘッダーにない列は「N 列目」。 */
export function columnName(model, column) {
  const name = model.headerAfter[column];
  return name && name.trim() ? name : `${column + 1} 列目`;
}
