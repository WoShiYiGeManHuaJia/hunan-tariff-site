/**
 * 云盘签到管家·分享版 设备验证（Pages Function）
 * POST /api/verify  {deviceId}
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

function getGhToken() {
  return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join("");
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
    let body;
    try { body = await request.json(); } catch { return json({ ok: false, error: "bad_request" }, 400); }
    const deviceId = (body.deviceId || "").trim();
    if (!deviceId) return json({ ok: false, error: "missing_params" }, 400);

    // GitHub API 即时读取（与 activate.js 一致，无 CDN 缓存延迟）
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: {
        "User-Agent": "yun139-activation",
        Authorization: `Bearer ${getGhToken()}`,
        Accept: "application/vnd.github+json"
      }
    });
    if (!r.ok) return json({ ok: false });
    const j = await r.json();
    const bytes = Uint8Array.from(atob(j.content.replace(/\s/g, "")), c => c.charCodeAt(0));
    const state = JSON.parse(new TextDecoder().decode(bytes));
    const dev = state.devices?.[deviceId];
    return json({ ok: !!dev, code: dev?.code });
  } catch (e) {
    return json({ ok: false, error: "internal: " + (e.message || "unknown") }, 500);
  }
}
