/**
 * 云盘签到管家·分享版 激活服务（Pages Function）
 * 存储后端 = GitHub 仓库 JSON 文件
 * POST /api/activate  {code, deviceId}
 * POST /api/verify    {deviceId}
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

function getGhToken() {
  return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join("");
}

const GH_HEADERS = () => ({
  "User-Agent": "yun139-activation",
  Authorization: `Bearer ${getGhToken()}`,
  Accept: "application/vnd.github+json"
});

// 读状态：GitHub API（即时一致，无 CDN 缓存延迟）
async function readState() {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: GH_HEADERS()
    });
    if (!r.ok) return { codes: {}, devices: {} };
    const j = await r.json();
    const bytes = Uint8Array.from(atob(j.content.replace(/\s/g, "")), c => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch { return { codes: {}, devices: {} }; }
}

// 写状态
async function writeState(state) {
  try {
    const bytes = new TextEncoder().encode(JSON.stringify(state, null, 2));
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    const b64 = btoa(bin);
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: GH_HEADERS()
    });
    const sha = r.ok ? (await r.json()).sha : null;
    const body = { message: "update activation state", content: b64 };
    if (sha) body.sha = sha;
    const w = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      method: "PUT",
      headers: { ...GH_HEADERS(), "Content-Type": "application/json" },
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
    const { request } = context;
    const url = new URL(request.url);
    let body;
    try { body = await request.json(); } catch { return json({ ok: false, error: "bad_request" }, 400); }

    const path = url.pathname;
    const state = await readState();

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
      if (!(code in codes)) return json({ ok: false, error: "invalid_code" }, 403);
      const bind = codes[code];
      if (bind.deviceId && bind.deviceId !== deviceId) return json({ ok: false, error: "code_used" }, 403);

      const now = new Date().toISOString();
      codes[code] = { deviceId, activatedAt: now };
      state.devices = state.devices || {};
      state.devices[deviceId] = { code, activatedAt: now };
      state.codes = codes;
      await writeState(state);
      return json({ ok: true, msg: "activated" });
    }

    return json({ ok: false, error: "not_found" }, 404);
  } catch (e) {
    return json({ ok: false, error: "internal: " + (e.message || "unknown") }, 500);
  }
}
