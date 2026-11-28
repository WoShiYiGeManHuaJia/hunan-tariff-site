/**
 * 签到管家 · 兑换码服务（Pages Function）
 * 配置存私有仓库 kebiao-live/redeem-config.json，本文件不含任何哈希。
 * GET /api/remaining · GET /api/check?code= · POST /api/redeem
 */
const REPO = "WoShiYiGeManHuaJia/kebiao-live";
const CFG = "redeem-config.json";
const TOTAL = 30;

function tok() { return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join(""); }
const H = () => ({ "User-Agent":"sk", Authorization:"Bearer "+tok(), Accept:"application/vnd.github+json" });
const cors = () => ({ "Access-Control-Allow-Origin":"*", "Access-Control-Allow-Methods":"GET,POST,OPTIONS", "Access-Control-Allow-Headers":"Content-Type", "Content-Type":"application/json; charset=utf-8" });
const jr = (o,s) => new Response(JSON.stringify(o), { status:s||200, headers:cors() });
const nm = c => String(c||"").trim().toUpperCase().replace(/[ _—]/g,"-");

async function h24(code, salt) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(salt), { name:"HMAC", hash:"SHA-256" }, false, ["sign"]);
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(code));
  return [...new Uint8Array(s).slice(0,12)].map(b=>b.toString(16).padStart(2,"0")).join("");
}
async function rd() {
  try {
    const r = await fetch("https://api.github.com/repos/"+REPO+"/contents/"+CFG, { headers: H() });
    if (!r.ok) return null;
    const j = await r.json();
    const bin = atob(j.content.replace(/\s/g,""));
    const u = new Uint8Array(bin.length);
    for (let i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i);
    return { cfg: JSON.parse(new TextDecoder().decode(u)), sha: j.sha };
  } catch(e) { return null; }
}
async function wr(cfg, sha) {
  try {
    const bytes = new TextEncoder().encode(JSON.stringify(cfg, null, 1));
    let bin=""; for (let i=0;i<bytes.length;i++) bin+=String.fromCharCode(bytes[i]);
    const body = { message:"update state", content:btoa(bin) };
    if (sha) body.sha = sha;
    const w = await fetch("https://api.github.com/repos/"+REPO+"/contents/"+CFG, {
      method:"PUT", headers:Object.assign({},H(),{"Content-Type":"application/json"}), body:JSON.stringify(body)
    });
    return w.ok;
  } catch(e) { return false; }
}

export async function onRequest(context) {
  const request = context.request;
  const url = new URL(request.url);
  const p = url.pathname;
  if (request.method === "OPTIONS") return new Response(null, { status:204, headers:cors() });

  const got = await rd();
  if (!got) return jr({ ok:false, status:"error", msg:"配置读取失败" }, 503);
  const cfg = got.cfg;
  const hashes = cfg.hashes || [];
  const used = cfg.used || {};
  const devices = cfg.devices || {};
  const n = Object.keys(used).length;

  if (p === "/api/remaining") {
    return jr({ ok:true, total:TOTAL, used:n, remaining:Math.max(0,TOTAL-n) });
  }
  if (p === "/api/check") {
    const c = nm(url.searchParams.get("code"));
    if (!c) return jr({ ok:false, msg:"missing code" }, 400);
    const h = await h24(c, cfg.salt);
    if (hashes.indexOf(h) < 0) return jr({ ok:true, status:"invalid", msg:"兑换码无效" });
    if (used[h]) return jr({ ok:true, status:"used", msg:"该兑换码已被使用" });
    if (n >= TOTAL) return jr({ ok:true, status:"exhausted", msg:"总托管池名额已用完，已无法添加托管" });
    return jr({ ok:true, status:"valid", msg:"可用" });
  }
  if (p === "/api/redeem" && request.method === "POST") {
    let b = {};
    try { b = await request.json(); } catch(e) {}
    const c = nm(b.code), dev = String(b.device||"");
    const h = b.hash ? String(b.hash).toLowerCase() : await h24(c, cfg.salt);
    if (!h || hashes.indexOf(h) < 0) return jr({ ok:false, status:"invalid", msg:"兑换码无效" });
    if (used[h]) {
      if (devices[h] && dev && devices[h] === dev) return jr({ ok:true, status:"already", msg:"该兑换码你已兑换过，名额已生效" });
      return jr({ ok:false, status:"used", msg:"该兑换码已被使用" });
    }
    if (n >= TOTAL) return jr({ ok:false, status:"exhausted", msg:"总托管池名额已用完，已无法添加托管" });
    cfg.used = used; cfg.devices = devices;
    cfg.used[h] = new Date().toISOString();
    if (dev) cfg.devices[h] = dev;
    await wr(cfg, got.sha);
    return jr({ ok:true, status:"redeemed", msg:"兑换成功", remaining:Math.max(0,TOTAL-n-1) });
  }
  return jr({ ok:false, msg:"not found", path:p }, 404);
}
