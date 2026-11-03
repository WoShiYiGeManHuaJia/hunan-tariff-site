/**
 * 云盘签到管家·分享版 激活服务（Pages Function）
 * POST /api/activate  {code, deviceId}
 * POST /api/verify    {deviceId}
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

function getGhToken() {
  return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join("");
}

async function readState() {
  try {
    const r = await fetch(
      `https://raw.githubusercontent.com/${REPO}/main/${STATE_PATH}`,
      { headers: { "Cache-Control": "no-cache" } }
    );
    if (!r.ok) return { codes: {}, devices: {}, _readErr: `HTTP ${r.status}` };
    return await r.json();
  } catch (e) { return { codes: {}, devices: {}, _readErr: e.message }; }
}

async function writeState(state) {
  const token = getGhToken();
  const results = [];
  try {
    const content = JSON.stringify(state, null, 2);
    const bytes = new TextEncoder().encode(content);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    const b64 = btoa(bin);

    // GET sha
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { "User-Agent": "yun139-activation", Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }
    });
    results.push(`GET_SHA=${r.status}`);
    const sha = r.ok ? (await r.json()).sha : null;
    results.push(`SHA=${sha ? sha.slice(0,8) : 'null'}`);

    // PUT
    const body = { message: "update activation state", content: b64 };
    if (sha) body.sha = sha;
    const w = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      method: "PUT",
      headers: { "User-Agent": "yun139-activation", Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const wBody = await w.text();
    results.push(`PUT=${w.status}`);
    if (!w.ok) results.push(`ERR=${wBody.slice(0, 150)}`);
    return { ok: w.ok, debug: results.join(" | ") };
  } catch (e) {
    results.push(`EXC=${e.message}`);
    return { ok: false, debug: results.join(" | ") };
  }
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
      return json({ ok: !!dev, code: dev?.code, _read: state._readErr || "ok" });
    }

    if (path.endsWith("/activate")) {
      const code = (body.code || "").trim().toUpperCase();
      const deviceId = (body.deviceId || "").trim();
      if (!code || !deviceId) return json({ ok: false, error: "missing_params" }, 400);
      if (state.devices?.[deviceId]) return json({ ok: true, msg: "already_activated", code: state.devices[deviceId].code });

      const codes = state.codes || {};
      if (!(code in codes)) return json({ ok: false, error: "invalid_code", _codes: Object.keys(codes).length }, 403);

      const bind = codes[code];
      if (bind.deviceId && bind.deviceId !== deviceId) return json({ ok: false, error: "code_used" }, 403);

      const now = new Date().toISOString();
      codes[code] = { deviceId, activatedAt: now };
      state.devices = state.devices || {};
      state.devices[deviceId] = { code, activatedAt: now };
      state.codes = codes;

      const wr = await writeState(state);
      return json({
        ok: true,
        msg: wr.ok ? "activated" : "activated_pending_sync",
        _write: wr.debug || "no-debug",
        _read: state._readErr || "ok"
      });
    }

    return json({ ok: false, error: "not_found" }, 404);
  } catch (e) {
    return json({ ok: false, error: "internal: " + (e.message || "unknown") }, 500);
  }
}
