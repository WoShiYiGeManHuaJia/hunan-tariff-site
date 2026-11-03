/**
 * 云盘签到管家·分享版 激活服务（Pages Function）
 * 存储后端 = GitHub 仓库 JSON 文件
 * POST /api/activate  {code, deviceId}
 * POST /api/verify    {deviceId}
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

function getGhToken() {
  try { return atob("Z2hwX0xKUm1XZzQ1YVhtc1hkazdDMG0zcWJRcVFURkJTQTBjWFhQSA=="); }
  catch { return ""; }
}

// 用 raw 接口读文件（返回纯文本 JSON，不需要 base64 解码）
async function readState(token) {
  try {
    const r = await fetch(
      `https://raw.githubusercontent.com/${REPO}/main/${STATE_PATH}`,
      { headers: { "Cache-Control": "no-cache" } }
    );
    if (!r.ok) return { codes: {}, devices: {} };
    return await r.json();
  } catch { return { codes: {}, devices: {} }; }
}

// 用 GitHub API 写文件（需要 base64）
async function writeState(state, token) {
  try {
    const content = JSON.stringify(state, null, 2);
    // 安全 UTF-8 → base64
    const bytes = new TextEncoder().encode(content);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    const b64 = btoa(bin);

    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }
    });
    const sha = r.ok ? (await r.json()).sha : null;
    const body = { message: "update activation state", content: b64 };
    if (sha) body.sha = sha;
    const w = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const wBody = await w.text();
    if (!w.ok) return `PUT_${w.status}: ${wBody.slice(0, 120)}`;
    return true;
  } catch (e) { return `ERR: ${e.message}`; }
}

function cors() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
  };
}
function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: cors() });
}

export async function onRequestPost(context) {
  try {
    const { request } = context;
    const url = new URL(request.url);
    const ghToken = getGhToken();
    if (!ghToken) return json({ ok: false, error: "server_misconfig" }, 500);

    let body;
    try { body = await request.json(); } catch { return json({ ok: false, error: "bad_request" }, 400); }

    const path = url.pathname;
    const state = await readState(ghToken);

    if (path.endsWith("/verify")) {
      const deviceId = (body.deviceId || "").trim();
      if (!deviceId) return json({ ok: false, error: "missing_params" }, 400);
      const dev = state.devices?.[deviceId];
      return json({ ok: !!dev, code: dev?.code });
    }

    if (path.endsWith("/activate")) {
      const code = (body.code || "").trim().toUpperCase();
      const deviceId = (body.deviceId || "").trim();
      if (!code || !deviceId) return json({ ok: false, error: "missing_params" }, 400);

      if (state.devices?.[deviceId]) return json({ ok: true, msg: "already_activated", code: state.devices[deviceId].code });

      const codes = state.codes || {};
      if (!(code in codes)) return json({ ok: false, error: "invalid_code", debug: `codes=${Object.keys(codes).length}` }, 403);

      const bind = codes[code];
      if (bind.deviceId && bind.deviceId !== deviceId) return json({ ok: false, error: "code_used" }, 403);

      const now = new Date().toISOString();
      codes[code] = { deviceId, activatedAt: now };
      state.devices = state.devices || {};
      state.devices[deviceId] = { code, activatedAt: now };
      state.codes = codes;
      const saved = await writeState(state, ghToken);
      return json({ ok: true, msg: saved ? "activated" : "activated_pending_sync" });
    }

    return json({ ok: false, error: "not_found" }, 404);
  } catch (e) {
    return json({ ok: false, error: "internal: " + (e.message || "unknown") }, 500);
  }
}
