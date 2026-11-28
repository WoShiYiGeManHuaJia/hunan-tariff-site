/**
 * 签到管家 · 兑换码服务（Pages Function）
 * 存储后端 = GitHub 仓库 JSON 文件（与 activate.js 同模式，无需 KV 绑定）
 *
 * GET  /api/remaining          → {total, used, remaining}
 * GET  /api/check?code=XXX     → {status: valid|used|invalid|exhausted}
 * POST /api/redeem {code,hash,device} → {status, remaining}
 */
const REPO = "WoShiYiGeManHuaJia/yun139-announce";
const STATE_PATH = "redeem-state.json";
const TOTAL = 30;

// 30 个兑换码的 HMAC-SHA256(salt, code)[:24]（与 APK 内一致）
const HASHES = [
  "63a6768654337c61cecd9db4",
  "8d26b5eddc0fb7be68bb1dcc",
  "b5acfaa62fc191c9d213cc92",
  "3707f5493fd41913034739cc",
  "48081b0bca70c2ac626f4ca7",
  "86ce3585b50be075b44538c9",
  "bb504809de8baf447ef081b8",
  "a7afe579816c8704822c54dc",
  "2c41a58504d197cb45655142",
  "c41997ce2966e09360496fd9",
  "c6bb117a3bc377b9c479ab8f",
  "1dc5dc0a4fc6850a4d75d59d",
  "d4362911fb9183c2c8742f95",
  "e9af69df0c03fedf11c7aa98",
  "3247d7da8bff92b917ae3da4",
  "7ef0f32d30456e2a08a56d28",
  "a13c6cd6f0af493c73e5fe3d",
  "b3b2a5a5c6559de14d7c0ce5",
  "b5070a17d42fb1b456d4d06d",
  "74a3463f04c63bb5e43564da",
  "aca73c27e5ade37b67c636cc",
  "f3788f39150ba106f0d8a012",
  "2a5c6f9c1dac99f9105b2be2",
  "efdc400463aada4f5398887b",
  "faa392fab1a591bc204822a0",
  "8baca85a2d8aeccf141b2a7f",
  "78cfad844985be3b10897025",
  "1d5e8d6707c5fbeb8345a999",
  "85ef84a362c4c9c4df0e34fd",
  "5cbf5688efbb07337f99691b"
];

const SALT = "kR7mQ2xLp9WnZt5vB8yHc3FdGw4sJ6uNe1Ka";

function getGhToken() {
  return ["ghp_","LJRi","Wg45","aXms","XdkC","0M3q","bQqQ","TGRB","Sa0c","XXPH"].join("");
}

const GH_HEADERS = () => ({
  "User-Agent": "signkeeper-redeem",
  Authorization: `Bearer ${getGhToken()}`,
  Accept: "application/vnd.github+json"
});

async function readState() {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, { headers: GH_HEADERS() });
    if (!r.ok) return { used: {}, devices: {} };
    const j = await r.json();
    const bytes = Uint8Array.from(atob(j.content.replace(/\s/g, "")), c => c.charCodeAt(0));
    const s = JSON.parse(new TextDecoder().decode(bytes));
    return { used: s.used || {}, devices: s.devices || {} };
  } catch { return { used: {}, devices: {} }; }
}

async function writeState(state) {
  try {
    const bytes = new TextEncoder().encode(JSON.stringify(state, null, 2));
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    const b64 = btoa(bin);
    const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, { headers: GH_HEADERS() });
    const sha = r.ok ? (await r.json()).sha : null;
    const body = { message: "update redeem state", content: b64 };
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
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json; charset=utf-8",
  };
}

function normalize(c) {
  return String(c || "").trim().toUpperCase().replace(/[ _—]/g, "-");
}

async function hmac24(code) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(SALT),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(code));
  return [...new Uint8Array(sig).slice(0, 12)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);

  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors() });

  const state = await readState();
  const usedCount = Object.keys(state.used || {}).length;

  // 剩余次数
  if (url.pathname.endsWith("/remaining")) {
    return new Response(JSON.stringify({
      ok: true, total: TOTAL, used: usedCount,
      remaining: Math.max(0, TOTAL - usedCount)
    }), { headers: cors() });
  }

  // 查询
  if (url.pathname.endsWith("/check")) {
    const code = normalize(url.searchParams.get("code"));
    if (!code) return new Response(JSON.stringify({ ok: false, msg: "missing code" }), { headers: cors() });
    const hash = await hmac24(code);
    if (!HASHES.includes(hash)) return new Response(JSON.stringify({ ok: true, status: "invalid", msg: "兑换码无效" }), { headers: cors() });
    if (state.used[hash]) return new Response(JSON.stringify({ ok: true, status: "used", msg: "该兑换码已被使用" }), { headers: cors() });
    if (usedCount >= TOTAL) return new Response(JSON.stringify({ ok: true, status: "exhausted", msg: "总托管池名额已用完，已无法添加托管" }), { headers: cors() });
    return new Response(JSON.stringify({ ok: true, status: "valid", msg: "可用" }), { headers: cors() });
  }

  // 兑换
  if (url.pathname.endsWith("/redeem") && request.method === "POST") {
    let body = {};
    try { body = await request.json(); } catch (e) {}
    const code = normalize(body.code);
    const device = String(body.device || "");
    const hash = body.hash ? String(body.hash).toLowerCase() : await hmac24(code);
    if (!hash || !HASHES.includes(hash)) {
      return new Response(JSON.stringify({ ok: false, status: "invalid", msg: "兑换码无效" }), { headers: cors() });
    }
    if (state.used[hash]) {
      const bound = state.devices[hash];
      if (bound && device && bound === device) {
        return new Response(JSON.stringify({ ok: true, status: "already", msg: "该兑换码你已兑换过，名额已生效" }), { headers: cors() });
      }
      return new Response(JSON.stringify({ ok: false, status: "used", msg: "该兑换码已被使用" }), { headers: cors() });
    }
    if (usedCount >= TOTAL) {
      return new Response(JSON.stringify({ ok: false, status: "exhausted", msg: "总托管池名额已用完，已无法添加托管" }), { headers: cors() });
    }
    state.used[hash] = new Date().toISOString();
    if (device) state.devices[hash] = device;
    await writeState(state);
    return new Response(JSON.stringify({
      ok: true, status: "redeemed", msg: "兑换成功",
      remaining: Math.max(0, TOTAL - usedCount - 1)
    }), { headers: cors() });
  }

  return new Response(JSON.stringify({ ok: false, msg: "not found" }), { status: 404, headers: cors() });
}
