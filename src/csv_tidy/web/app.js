// 画面の入口。操作と処理を結びつける（設計書 6.2、8 章、10.2）。

import { ApiError, exportCsv, tidy } from "./api.js";
import {
  INPUT_ENCODING_LABELS,
  MAX_BYTES,
  buildModel,
  changeIndexAtOrAfter,
  downloadName,
  formatSize,
  newView,
  pageOf,
  state,
} from "./state.js";
import { renderDiff } from "./views/diff.js";
import { el, replace } from "./views/dom.js";
import { renderIssues } from "./views/issues.js";
import { renderSummary } from "./views/summary.js";

const $ = (id) => document.getElementById(id);

const ui = {
  dropzone: $("dropzone"),
  fileEmpty: $("file-empty"),
  fileInfo: $("file-info"),
  fileName: $("file-name"),
  fileMeta: $("file-meta"),
  fileLimit: $("file-limit"),
  chooseFile: $("choose-file"),
  fileInput: $("file-input"),
  inputEncoding: $("input-encoding"),
  trim: $("opt-trim"),
  removeEmpty: $("opt-remove-empty"),
  dedupe: $("opt-dedupe"),
  dedupeNote: $("dedupe-note"),
  outputEncoding: $("output-encoding"),
  newlines: document.querySelectorAll('input[name="newline"]'),
  download: $("download"),
  downloadName: $("download-name"),
  exportReason: $("export-reason"),
  viewEmpty: $("view-empty"),
  viewLoading: $("view-loading"),
  viewError: $("view-error"),
  viewResult: $("view-result"),
  errorTitle: $("error-title"),
  errorMessage: $("error-message"),
  errorChecks: $("error-checks"),
  errorCode: $("error-code"),
  summary: $("summary"),
  tabDiff: $("tab-diff"),
  tabIssues: $("tab-issues"),
  panelDiff: $("panel-diff"),
  panelIssues: $("panel-issues"),
};

// 処理中に次の操作があったら、前の通信を打ち切る（画面設計書 5 章）
let controller = null;

// ---- ファイルを選ぶ ----

function chooseFile(file) {
  if (!file) return;
  if (controller) controller.abort();
  state.view = newView();
  state.result = null;
  state.model = null;
  state.exportError = null;
  // 大きすぎるファイルは送らずに止める（FR-02、設計書 D5）
  if (file.size > MAX_BYTES) {
    state.file = null;
    state.status = "failed";
    state.error = new ApiError(
      "file_too_large",
      `ファイルが大きすぎます（${formatSize(file.size)}）。${MAX_BYTES.toLocaleString()} バイト（10MB）以下のファイルを選んでください。`,
      { limit: MAX_BYTES, name: file.name },
    );
    render();
    return;
  }
  state.file = file;
  process();
}

ui.chooseFile.addEventListener("click", () => ui.fileInput.click());
ui.fileInput.addEventListener("change", () => {
  chooseFile(ui.fileInput.files[0]);
  ui.fileInput.value = ""; // 同じファイルを選び直しても change が起きるようにする
});

ui.dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  ui.dropzone.classList.add("drag");
});
ui.dropzone.addEventListener("dragleave", () => ui.dropzone.classList.remove("drag"));
ui.dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  ui.dropzone.classList.remove("drag");
  chooseFile(event.dataTransfer.files[0]);
});
// 受け口の外に落としたとき、ブラウザがファイルを開いて画面が切り替わらないようにする
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

// ---- 設定を変える（すぐ処理し直す。画面設計書 5 章） ----

function onOptionChange(update) {
  update(state.options);
  state.exportError = null;
  if (state.file) process();
}

ui.inputEncoding.addEventListener("change", () =>
  onOptionChange((o) => (o.input_encoding = ui.inputEncoding.value || null)),
);
ui.trim.addEventListener("change", () => onOptionChange((o) => (o.trim = ui.trim.checked)));
ui.removeEmpty.addEventListener("change", () => onOptionChange((o) => (o.remove_empty = ui.removeEmpty.checked)));
ui.dedupe.addEventListener("change", () => onOptionChange((o) => (o.dedupe = ui.dedupe.checked)));
ui.outputEncoding.addEventListener("change", () =>
  onOptionChange((o) => (o.output_encoding = ui.outputEncoding.value)),
);
for (const radio of ui.newlines) {
  radio.addEventListener("change", () => onOptionChange((o) => (o.newline = radio.value)));
}

// ---- 整形する ----

async function process() {
  if (controller) controller.abort();
  const current = new AbortController();
  controller = current;
  const options = { ...state.options };
  state.status = "loading";
  render();
  try {
    const result = await tidy(state.file, options, current.signal);
    if (controller !== current) return;
    const firstResult = state.model === null;
    state.result = result;
    state.resultOptions = options;
    state.model = buildModel(result);
    state.error = null;
    state.status = "ready";
    const view = newView();
    // 新しいファイルでは差分タブから。設定の変更では、見ていたタブと表示の切り替えを保つ
    if (!firstResult) {
      view.tab = state.view.tab;
      view.mode = state.view.mode;
    }
    // ダウンロードできないときは、理由が分かる課題タブを開く（画面設計書 4.2）
    if (!result.output.exportable) view.tab = "issues";
    state.view = view;
  } catch (error) {
    if (error.name === "AbortError" || controller !== current) return;
    state.status = "failed";
    state.error = error instanceof ApiError ? error : new ApiError("unexpected", String(error));
  } finally {
    if (controller === current) controller = null;
  }
  render();
}

// ---- ダウンロード（設計書 8.3） ----

ui.download.addEventListener("click", async () => {
  if (!canDownload()) return;
  state.exporting = true;
  state.exportError = null;
  renderSidebar();
  const name = downloadName(state.file.name);
  try {
    const blob = await exportCsv(state.file, state.resultOptions, undefined);
    // 保存する名前はブラウザ側で付ける（設計書 D7）
    const url = URL.createObjectURL(blob);
    const link = el("a", { href: url, download: name });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  } catch (error) {
    state.exportError = error instanceof ApiError ? error.message : "ダウンロードできませんでした。";
  } finally {
    state.exporting = false;
    renderSidebar();
  }
});

function canDownload() {
  return state.status === "ready" && state.result.output.exportable && !state.exporting;
}

// ---- 表示 ----

function render() {
  renderSidebar();
  renderMain();
}

function renderSidebar() {
  const { file, result, status } = state;
  const hasFile = file !== null;

  ui.dropzone.classList.toggle("has-file", hasFile);
  ui.fileEmpty.hidden = hasFile;
  ui.fileInfo.hidden = !hasFile;
  ui.fileLimit.hidden = hasFile;
  ui.chooseFile.textContent = hasFile ? "別のファイルを選ぶ" : "ファイルを選ぶ";
  if (hasFile) {
    ui.fileName.textContent = file.name;
    const lines = result && result.records.length ? result.records[result.records.length - 1].line_end : null;
    ui.fileMeta.textContent = formatSize(file.size) + (lines ? ` ・ ${lines.toLocaleString()} 行` : "");
  }

  for (const section of document.querySelectorAll(".needs-file")) {
    section.classList.toggle("disabled", !hasFile);
    for (const control of section.querySelectorAll("input, select")) control.disabled = !hasFile;
  }

  // 自動判定の結果を選択肢に出す（画面設計書 3 章）
  const auto = ui.inputEncoding.options[0];
  auto.textContent =
    result && result.input.auto_detected && status !== "failed"
      ? `自動判定（${INPUT_ENCODING_LABELS[result.input.encoding]} と判定）`
      : "自動判定";

  const stats = result && result.stats;
  const showDup = status === "ready" && stats && !state.resultOptions.dedupe && stats.duplicates_found > 0;
  ui.dedupeNote.hidden = !showDup;
  if (showDup) ui.dedupeNote.textContent = `重複が ${stats.duplicates_found} 件あります（まだ削除していません）`;

  ui.download.disabled = !canDownload();
  ui.download.textContent = state.exporting ? "ダウンロード中…" : "ダウンロード";
  ui.downloadName.textContent = hasFile && status !== "failed" ? downloadName(file.name) : "";
  let reason = "";
  if (status === "ready" && !result.output.exportable) {
    reason =
      `CP932 で表せない文字が ${stats.unencodable_chars} 件あります。` +
      "課題タブで場所を確認し、元データを直すか、出力を UTF-8 にしてください。";
  } else if (state.exportError) {
    reason = state.exportError;
  }
  ui.exportReason.textContent = reason;
}

function renderMain() {
  const { status, model } = state;
  ui.viewEmpty.hidden = status !== "empty";
  ui.viewLoading.hidden = status !== "loading";
  ui.viewLoading.textContent = model
    ? "処理中です…（設定を変えたので、もう一度処理しています）"
    : "処理中です…";
  ui.viewError.hidden = status !== "failed";
  if (status === "failed") renderError(state.error);
  const showResult = model !== null && (status === "ready" || status === "loading");
  ui.viewResult.hidden = !showResult;
  ui.viewResult.classList.toggle("dim", status === "loading");
  if (showResult) renderResult();
}

function renderResult() {
  const { model, view } = state;
  renderSummary(ui.summary, model, state.resultOptions);

  ui.tabIssues.textContent = `課題（${model.result.issues.length}）`;
  const onDiff = view.tab === "diff";
  ui.tabDiff.classList.toggle("on", onDiff);
  ui.tabIssues.classList.toggle("on", !onDiff);
  ui.tabDiff.setAttribute("aria-selected", String(onDiff));
  ui.tabIssues.setAttribute("aria-selected", String(!onDiff));
  ui.panelDiff.hidden = !onDiff;
  ui.panelIssues.hidden = onDiff;

  if (onDiff) {
    renderDiff(ui.panelDiff, model, view, diffHandlers);
  } else {
    renderIssues(ui.panelIssues, model, view, state.resultOptions, issueHandlers);
  }
}

ui.tabDiff.addEventListener("click", () => switchTab("diff"));
ui.tabIssues.addEventListener("click", () => switchTab("issues"));

function switchTab(tab) {
  if (!state.model) return;
  state.view.tab = tab;
  renderResult();
}

/** 強調している行を画面の中央に出す。 */
function scrollToFocus() {
  const row = ui.panelDiff.querySelector("tr.focus");
  if (row) row.scrollIntoView({ block: "center" });
}

/** 指定した行へ移動して強調する。「変更箇所のみ」で隠れている行なら「全行」に広げる（画面設計書 4.4）。 */
function focusRecord(record) {
  const { model, view } = state;
  view.tab = "diff";
  view.focus = record;
  const index = changeIndexAtOrAfter(model, record);
  view.cursor = model.changed[index] === record ? index : null;
  let page = pageOf(model, view.mode, record);
  if (page === null) {
    view.mode = "all";
    page = pageOf(model, "all", record);
  }
  view.page = page;
  renderResult();
  scrollToFocus();
}

const diffHandlers = {
  onMode(mode) {
    const { model, view } = state;
    view.mode = mode;
    view.page = view.focus === null ? 0 : (pageOf(model, mode, view.focus) ?? 0);
    renderResult();
    scrollToFocus();
  },
  onMove(step) {
    const { model, view } = state;
    const count = model.changed.length;
    if (count === 0) return;
    let cursor;
    if (view.cursor !== null) cursor = view.cursor + step;
    else if (view.focus !== null) cursor = changeIndexAtOrAfter(model, view.focus) + (step > 0 ? 0 : -1);
    else cursor = step > 0 ? 0 : count - 1;
    focusRecord(model.changed[Math.min(Math.max(cursor, 0), count - 1)]);
  },
  onPage(page) {
    state.view.page = page;
    renderResult();
    ui.panelDiff.scrollIntoView({ block: "start" });
  },
};

const issueHandlers = {
  onJump: focusRecord,
  onMore(code, shown) {
    state.view.shown[code] = shown;
    renderResult();
  },
};

// ---- エラーの表示（画面設計書 6 章） ----

function renderError(error) {
  const { title, checks } = describeError(error);
  ui.errorTitle.textContent = title;
  ui.errorMessage.textContent = error.message;
  replace(ui.errorChecks, checks.map((text) => el("li", {}, text)));
  ui.errorCode.textContent = `エラーの種類: ${error.code}`;
}

const RETRY_ENCODING = "左の「読み込み」で文字コードを指定し直す（自動判定を誤った場合に解決することがあります）";

function describeError(error) {
  switch (error.code) {
    case "file_too_large":
      return {
        title: "ファイルが大きすぎます",
        checks: ["10MB（10,485,760 バイト）以下のファイルを選んでいるか", "大きなファイルは分けてから読み込む"],
      };
    case "empty_data":
      return { title: "データがありません", checks: ["中身のある CSV ファイルを選んでいるか"] };
    case "not_csv":
      return error.extra.looks_like_xlsx
        ? { title: "Excel のファイルです", checks: ["Excel で開き、「名前を付けて保存」で CSV 形式を選んで保存し直す"] }
        : { title: "CSV ではないファイルです", checks: ["CSV 形式で保存したファイルを選んでいるか"] };
    case "decode_failed":
      return error.extra.encoding
        ? { title: "指定した文字コードで読み込めません", checks: ["別の文字コードを選ぶか、「自動判定」に戻す"] }
        : { title: "文字コードを判定できません", checks: ["UTF-8 か CP932（Shift_JIS）で保存したファイルを選んでいるか", RETRY_ENCODING] };
    case "csv_syntax":
      return {
        title: "CSV の書き方に誤りがあります",
        checks: [`元のファイルの ${error.extra.line} 行目付近で、「"」（ダブルクォート）の数が対になっているか`, RETRY_ENCODING],
      };
    case "network":
      return {
        title: "サーバーに接続できません",
        checks: ["csv-tidy を起動しているか（uv run csv-tidy）", "起動した画面と同じアドレス（http://127.0.0.1:8000）を開いているか"],
      };
    default:
      return { title: "処理できませんでした", checks: ["画面を読み込み直して、もう一度試す"] };
  }
}

render();
