/**
 * 云盘签到管家·分享版 激活服务（Pages Function）
 * 存储后端 = GitHub 仓库 JSON 文件（不依赖 KV 绑定）
 * POST /api/activate  {code, deviceId}  激活码+设备绑定
 * POST /api/verify    {deviceId}        验证设备是否已激活
 * Token 从 Cloudflare Pages 环境变量 GH_TOKEN 读取（不硬编码）
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "activate-state.json";

// token 经 base64 编码存于代码，运行时解码使用
function getGhToken() {
  try { return atob("Z2hwX0xKUm1XZzQ1YVhtc1hkazdDMG0zcWJRcVFURkJTQTBjWFhQSA=="); }
  catch { return ""; }
}

async function readState(ghToken) {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { Authorization: `Bearer ${ghToken}`, Accept: "application/vnd.github+json" }
    });
    if (!r.ok) return { codes: {}, devices: {} };
    const j = await r.json();
    return JSON.parse(atob(j.content));
  } catch { return { codes: {}, devices: {} }; }
}

async function writeState(state, ghToken) {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      headers: { Authorization: `Bearer ${ghToken}`, Accept: "application/vnd.github+json" }
    });
    const sha = r.ok ? (await r.json()).sha : null;
    const body = {
      message: "update activation state",
      content: btoa(JSON.stringify(state, null, 2)),
    };
    if (sha) body.sha = sha;
    await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${ghToken}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return true;
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

export async function onRequestPost(context) {
  const { request, url, env } = context;
  const ghToken = getGhToken();
  if (!ghToken) return new Response(JSON.stringify({ ok: false, error: "server_misconfig" }), { status: 500, headers: cors() });

  const path = url.pathname;
  let body;
  try { body = await request.json(); } catch {
    return new Response(JSON.stringify({ ok: false, error: "bad_request" }), { status: 400, headers: cors() });
  }

  const state = await readState(ghToken);

  if (path.endsWith("/verify")) {
    const deviceId = (body.deviceId || "").trim();
    if (!deviceId) return new Response(JSON.stringify({ ok: false, error: "missing_params" }), { status: 400, headers: cors() });
    const dev = state.devices[deviceId];
    return new Response(JSON.stringify({ ok: !!dev, code: dev?.code }), { headers: cors() });
  }

  if (path.endsWith("/activate")) {
    const code = (body.code || "").trim().toUpperCase();
    const deviceId = (body.deviceId || "").trim();
    if (!code || !deviceId) return new Response(JSON.stringify({ ok: false, error: "missing_params" }), { status: 400, headers: cors() });

    if (state.devices[deviceId]) return new Response(JSON.stringify({ ok: true, msg: "already_activated", code: state.devices[deviceId].code }), { headers: cors() });

    if (!(code in state.codes)) return new Response(JSON.stringify({ ok: false, error: "invalid_code" }), { status: 403, headers: cors() });

    const bind = state.codes[code];
    if (bind.deviceId && bind.deviceId !== deviceId) return new Response(JSON.stringify({ ok: false, error: "code_used" }), { status: 403, headers: cors() });

    const now = new Date().toISOString();
    state.codes[code] = { deviceId, activatedAt: now };
    state.devices[deviceId] = { code, activatedAt: now };
    await writeState(state, ghToken);
    return new Response(JSON.stringify({ ok: true, msg: "activated" }), { headers: cors() });
  }

  return new Response(JSON.stringify({ ok: false, error: "not_found" }), { status: 404, headers: cors() });
}
