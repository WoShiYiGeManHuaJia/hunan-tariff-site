/**
 * 云盘签到管家·分享版 设备验证（Pages Function）
 * POST /api/verify  {deviceId}
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

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

    // 读状态：raw 接口免鉴权
    const r = await fetch(
      `https://raw.githubusercontent.com/${REPO}/main/${STATE_PATH}`,
      { headers: { "Cache-Control": "no-cache" } }
    );
    if (!r.ok) return json({ ok: false });
    const state = await r.json();
    const dev = state.devices?.[deviceId];
    return json({ ok: !!dev, code: dev?.code });
  } catch (e) {
    return json({ ok: false, error: "internal: " + (e.message || "unknown") }, 500);
  }
}
