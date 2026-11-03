/**
 * 云盘签到管家·分享版 设备验证（Pages Function）
 * 存储后端 = GitHub 仓库 JSON 文件
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

export async function onRequestPost(context) {
  const { request, env } = context;
  const ghToken = env.GH_TOKEN;
  if (!ghToken) return new Response(JSON.stringify({ ok: false, error: "server_misconfig" }), { status: 500, headers: cors() });

  let body;
  try { body = await request.json(); } catch {
    return new Response(JSON.stringify({ ok: false, error: "bad_request" }), { status: 400, headers: cors() });
  }
  const deviceId = (body.deviceId || "").trim();
  if (!deviceId) return new Response(JSON.stringify({ ok: false, error: "missing_params" }), { status: 400, headers: cors() });

  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { Authorization: `Bearer ${ghToken}`, Accept: "application/vnd.github+json" }
    });
    if (!r.ok) return new Response(JSON.stringify({ ok: false }), { headers: cors() });
    const j = await r.json();
    const state = JSON.parse(atob(j.content));
    const dev = state.devices[deviceId];
    return new Response(JSON.stringify({ ok: !!dev, code: dev?.code }), { headers: cors() });
  } catch {
    return new Response(JSON.stringify({ ok: false }), { headers: cors() });
  }
}
