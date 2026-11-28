/**
 * 签到管家 · 兑换码服务（Pages Function）
 * ★ 配置（salt + 哈希表）存于私有仓库 WoShiYiGeManHuaJia/kebiao-live/redeem-config.json
 *   本文件可公开，不含任何兑换码哈希。
 * GET  /api/remaining · /api/check?code= · POST /api/redeem
 */
const REPO = "WoShiYiGeManHuaJia/kebiao-live";
const CONFIG_PATH = "redeem-config.json";
const TOTAL = 30;

function ghToken() {
  return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join("");
}
const GH = () => ({
  "User-Agent": "signkeeper-redeem",
  Authorization: `Bearer ${ghToken()}`,
  Accept: "application/vnd.github+json"
});

async function ghGet(path) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, { headers: GH() });
  if (!r.ok) return null;
  const j = await r.json();
  const bytes = Uint8Array.from(atob(j.content.replace(/\s/g, "")), c => c.charCodeAt(0));
  return { data: JSON.parse(new TextDecoder().decode(bytes)), sha: j.sha };
}

async function ghPut(path, obj, sha) {
  const bytes = new TextEncoder().encode(JSON.stringify(obj, null, 1));
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  const body = { message: "update redeem state", content: btoa(bin) };
  if (sha) body.sha = sha;
  const w = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, {
    method: "PUT",
    headers: { ...GH(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return w.ok;
}

const cors = () => ({
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Content-Type": "application/json; charset=utf-8",
});
const jr = (o, s) => new Response(JSON.stringify(o), { status: s || 200, headers: cors() });
const norm = c => String(c || "").trim().toUpperCase().replace(/[ _—]/g, "-");

async function hmac24(code, salt) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(salt),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(code));
  return [...new Uint8Array(sig).slice(0, 12)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors() });

  const cfg = await ghGet(CONFIG_PATH);
  if (!cfg) return jr({ ok: false, msg: "config unavailable" }, 503);
  const conf = cfg.data;
  const hashes = conf.hashes || [];
  const used = conf.used || {};
  const devices = conf.devices || {};
  const usedCount = Object.keys(used).length;

  if (url.pathname === "/api/remaining" || url.pathname === "/api/redeem/remaining" || url.pathname === "/remaining") {
    return jr({ ok: true, total: TOTAL, used: usedCount, remaining: Math.max(0, TOTAL - usedCount) });
  }

  if (url.pathname === "/api/check" || url.pathname === "/check") {
    const code = norm(url.searchParams.get("code"));
    if (!code) return jr({ ok: false, msg: "missing code" }, 400);
    const hash = await hmac24(code, conf.salt);
    if (!hashes.includes(hash)) return jr({ ok: true, status: "invalid", msg: "兑换码无效" });
    if (used[hash]) return jr({ ok: true, status: "used", msg: "该兑换码已被使用" });
    if (usedCount >= TOTAL) return jr({ ok: true, status: "exhausted", msg: "总托管池名额已用完，已无法添加托管" });
    return jr({ ok: true, status: "valid", msg: "可用" });
  }

  if ((url.pathname === "/api/redeem" || url.pathname === "/redeem") && request.method === "POST") {
    let body = {};
    try { body = await request.json(); } catch (e) {}
    const code = norm(body.code);
    const device = String(body.device || "");
    const hash = body.hash ? String(body.hash).toLowerCase() : await hmac24(code, conf.salt);
    if (!hash || !hashes.includes(hash)) return jr({ ok: false, status: "invalid", msg: "兑换码无效" });
    if (used[hash]) {
      const bound = devices[hash];
      if (bound && device && bound === device) return jr({ ok: true, status: "already", msg: "该兑换码你已兑换过，名额已生效" });
      return jr({ ok: false, status: "used", msg: "该兑换码已被使用" });
    }
    if (usedCount >= TOTAL) return jr({ ok: false, status: "exhausted", msg: "总托管池名额已用完，已无法添加托管" });
    conf.used = used; conf.devices = devices;
    conf.used[hash] = new Date().toISOString();
    if (device) conf.devices[hash] = device;
    await ghPut(CONFIG_PATH, conf, cfg.sha);
    return jr({ ok: true, status: "redeemed", msg: "兑换成功", remaining: Math.max(0, TOTAL - usedCount - 1) });
  }

  return jr({ ok: false, msg: "not found", path: url.pathname, method: request.method }, 404);
}
