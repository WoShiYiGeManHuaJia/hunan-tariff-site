/**
 * 云盘签到管家·分享版 激活服务（Pages Function）
 * 存储后端 = GitHub 仓库 JSON 文件
 * POST /api/activate  {code, deviceId}  激活码+设备绑定
 * POST /api/verify    {deviceId}        验证设备是否已激活
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

function getGhToken() {
  try { return atob("Z2hwX0xKUm1XZzQ1YVhtc1hkazdDMG0zcWJRcVFURkJTQTBjWFhQSA=="); }
  catch { return ""; }
}

// 安全的 UTF-8 base64 编解码（替代裸 btoa/atob，防止 Unicode 崩溃）
function b64encode(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
function b64decode(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

async function readState(token) {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }
    });
    if (!r.ok) return { codes: {}, devices: {} };
    const j = await r.json();
    return JSON.parse(b64decode(j.content));
  } catch { return { codes: {}, devices: {} }; }
}

async function writeState(state, token) {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }
    });
    const sha = r.ok ? (await r.json()).sha : null;
    const body = { message: "update activation state", content: b64encode(JSON.stringify(state, null, 2)) };
    if (sha) body.sha = sha;
    const w = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return w.ok;
  } catch { return false; }
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
    const { request, url } = context;
    const ghToken = getGhToken();
    if (!ghToken) return json({ ok: false, error: "server_misconfig" }, 500);

    const path = url.pathname;
    let body;
    try { body = await request.json(); } catch { return json({ ok: false, error: "bad_request" }, 400); }

    const state = await readState(ghToken);

    if (path.endsWith("/verify")) {
      const deviceId = (body.deviceId || "").trim();
      if (!deviceId) return json({ ok: false, error: "missing_params" }, 400);
      const dev = state.devices[deviceId];
      return json({ ok: !!dev, code: dev?.code });
    }

    if (path.endsWith("/activate")) {
      const code = (body.code || "").trim().toUpperCase();
      const deviceId = (body.deviceId || "").trim();
      if (!code || !deviceId) return json({ ok: false, error: "missing_params" }, 400);
      if (state.devices[deviceId]) return json({ ok: true, msg: "already_activated", code: state.devices[deviceId].code });
      if (!(code in state.codes)) return json({ ok: false, error: "invalid_code" }, 403);
      const bind = state.codes[code];
      if (bind.deviceId && bind.deviceId !== deviceId) return json({ ok: false, error: "code_used" }, 403);

      const now = new Date().toISOString();
      state.codes[code] = { deviceId, activatedAt: now };
      state.devices[deviceId] = { code, activatedAt: now };
      const saved = await writeState(state, ghToken);
      return json({ ok: true, msg: saved ? "activated" : "activated_pending_sync" });
    }

    return json({ ok: false, error: "not_found" }, 404);
  } catch (e) {
    return json({ ok: false, error: "internal: " + (e.message || "unknown") }, 500);
  }
}
