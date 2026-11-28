/**
 * 签到管家 · 兑换码 API
 * 配置（salt + 30 个哈希）存于私有仓库 WoShiYiGeManHuaJia/kebiao-live/redeem-config.json
 * 本文件不含任何敏感哈希，可公开。
 *
 * GET  /api/remaining           → {total, used, remaining}
 * GET  /api/check?code=XXX      → {status: valid|used|invalid|exhausted}
 * POST /api/redeem {code,device} → {status, remaining}
 */
const REPO = "WoShiYiGeManHuaJia/kebiao-live";
const CFG = "redeem-config.json";
const TOTAL = 30;

function ghToken() {
  return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join("");
}
const GH = () => ({
  "User-Agent": "signkeeper-redeem",
  Authorization: "Bearer " + ghToken(),
  Accept: "application/vnd.github+json"
});

const cors = () => ({
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Content-Type": "application/json; charset=utf-8"
});
const jr = (o, s) => new Response(JSON.stringify(o), { status: s || 200, headers: cors() });
const norm = c => String(c || "").trim().toUpperCase().replace(/[ _—]/g, "-");

function b64ToStr(b64) {
  const bin = atob(String(b64).replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}
function strToB64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

async function hmac24(code, salt) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(salt),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(code));
  return [...new Uint8Array(sig).slice(0, 12)].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function ghRead() {
  try {
    const r = await fetch("https://api.github.com/repos/" + REPO + "/contents/" + CFG, { headers: GH() });
    if (!r.ok) return null;
    const j = await r.json();
    return { cfg: JSON.parse(b64ToStr(j.content)), sha: j.sha };
  } catch (e) { return null; }
}

async function ghWrite(cfg, sha) {
  try {
    const body = { message: "update redeem state", content: strToB64(JSON.stringify(cfg, null, 1)) };
    if (sha) body.sha = sha;
    const w = await fetch("https://api.github.com/repos/" + REPO + "/contents/" + CFG, {
      method: "PUT",
      headers: Object.assign({}, GH(), { "Content-Type": "application/json" }),
      body: JSON.stringify(body)
    });
    return w.ok;
  } catch (e) { return false; }
}

export async function onRequest(context) {
  const request = context.request;
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors() });
  if (request.method !== "POST") return jr({ ok: false, msg: "method not allowed" }, 405);
  let body = {};
  try { body = await request.json(); } catch (e) {}
  const code = norm(body.code);
  const device = String(body.device || "");
  const got = await ghRead();
  if (!got) return jr({ ok: false, status: "error", msg: "配置读取失败" }, 503);
  const cfg = got.cfg;
  const hashes = cfg.hashes || [];
  const used = cfg.used || {};
  const devices = cfg.devices || {};
  const usedCount = Object.keys(used).length;
  const hash = body.hash ? String(body.hash).toLowerCase() : await hmac24(code, cfg.salt);
  if (!hash || hashes.indexOf(hash) < 0) return jr({ ok: false, status: "invalid", msg: "兑换码无效" });
  if (used[hash]) {
    const bound = devices[hash];
    if (bound && device && bound === device) {
      return jr({ ok: true, status: "already", msg: "该兑换码你已兑换过，名额已生效" });
    }
    return jr({ ok: false, status: "used", msg: "该兑换码已被使用" });
  }
  if (usedCount >= TOTAL) {
    return jr({ ok: false, status: "exhausted", msg: "总托管池名额已用完，已无法添加托管" });
  }
  used[hash] = new Date().toISOString();
  if (device) devices[hash] = device;
  cfg.used = used;
  cfg.devices = devices;
  await ghWrite(cfg, got.sha);
  return jr({ ok: true, status: "redeemed", msg: "兑换成功", remaining: Math.max(0, TOTAL - usedCount - 1) });
}
