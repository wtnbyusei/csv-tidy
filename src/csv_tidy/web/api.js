// サーバーとの通信（設計書 11 章）。サーバーは状態を持たないので、毎回ファイルと設定を送る（NFR-08）。

/** 通信やサーバーのエラー。code は設計書 11.3 の種類（通信できないときは "network"）。 */
export class ApiError extends Error {
  constructor(code, message, extra = {}) {
    super(message);
    this.code = code;
    this.extra = extra;
  }
}

function formData(file, options) {
  const body = new FormData();
  body.append("file", file);
  body.append("options", JSON.stringify(options));
  return body;
}

async function post(path, file, options, signal) {
  let response;
  try {
    response = await fetch(path, { method: "POST", body: formData(file, options), signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("network", "サーバーに接続できませんでした。");
  }
  if (!response.ok) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      // JSON でない応答（想定外）。下で共通の形にする
    }
    const error = body && body.error;
    if (error && typeof error.code === "string") {
      const { code, message, ...extra } = error;
      throw new ApiError(code, String(message ?? ""), extra);
    }
    throw new ApiError("unexpected", `サーバーが想定外の応答を返しました（HTTP ${response.status}）。`);
  }
  return response;
}

/** 整形結果（設計書 11.2）を返す。 */
export async function tidy(file, options, signal) {
  const response = await post("/api/tidy", file, options, signal);
  return response.json();
}

/** 整形後の CSV を Blob で返す。 */
export async function exportCsv(file, options, signal) {
  const response = await post("/api/export", file, options, signal);
  return response.blob();
}
