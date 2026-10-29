/**
 * yun139-relay —— 云盘签到面板的中转层
 *
 * 作用：GitHub 令牌只放在本 Worker 的环境变量（加密存储）里，
 * 网页源码里永远不会出现令牌，谁翻源码都拿不到。
 *
 * 对外接口（全部无需任何凭据即可调用，令牌由本服务附加）：
 *   POST /gh/dispatch           body: {type, payload}   触发后台任务
 *   GET  /gh/file?path=xxx      读取仓库文件（返回 JSON）
 *   PUT  /gh/file               写入仓库文件（保管箱配置等）
 *   GET  /gh/ping               健康检查
 *
 * 环境变量（在 Cloudflare 面板里设置，Secret 类型）：
 *   GH_TOKEN   你的 GitHub 令牌（只存在这里）
 *   可选：
 *   GH_OWNER   默认 WoShiYiGeManHuaJia
 *   GH_REPO    默认 yun139-ghpanel
 *   RELAY_KEY  可选，填了之后请求需带 X-Relay-Key
 */

const GH = 'https://api.github.com';

// 允许触发的事件白名单：即便被滥用，也只能在面板命令范围内
const ALLOWED_TYPES = new Set([
  'status', 'list', 'save_token', 'del_account',
  'refresh', 'sign', 'task', 'receive', 'daily',
  'send_test', 'check_pass', 'notify_save', 'notify_read',
  'migrate_notify', 'probe16', 'diag', 'verify',
]);

// 允许读写的路径前缀：只碰 data/ 目录
function pathAllowed(p) {
  if (typeof p !== 'string') return false;
  if (!p.startsWith('data/')) return false;
  if (p.includes('..')) return false;
  if (p.includes('//')) return false;
  return true;
}

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,PUT,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type,X-Relay-Key',
  'Access-Control-Max-Age': '86400',
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json; charset=utf-8' },
  });
}

// 极简内存限流：同一 IP 每分钟最多 30 次
const hits = new Map();
function rateOk(ip) {
  const now = Date.now();
  const arr = (hits.get(ip) || []).filter(t => now - t < 60000);
  arr.push(now);
  hits.set(ip, arr);
  if (hits.size > 5000) hits.clear();
  return arr.length <= 30;
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: CORS });

    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    if (!rateOk(ip)) return json({ ok: false, msg: '请求过于频繁，稍后再试' }, 429);

    // 可选的访问钥匙
    if (env.RELAY_KEY) {
      const k = request.headers.get('X-Relay-Key') || '';
      if (k !== env.RELAY_KEY) return json({ ok: false, msg: 'relay key 不正确' }, 401);
    }

    if (!env.GH_TOKEN) return json({ ok: false, msg: '服务端未配置 GH_TOKEN' }, 500);

    const url = new URL(request.url);
    const owner = env.GH_OWNER || 'WoShiYiGeManHuaJia';
    const repo = env.GH_REPO || 'yun139-ghpanel';
    const auth = { Authorization: 'token ' + env.GH_TOKEN, Accept: 'application/vnd.github+json', 'User-Agent': 'yun139-relay' };

    try {
      // ---- 健康检查（透传 GitHub 响应，前端判断逻辑不用改）----
      if (url.pathname === '/gh/ping') {
        const r = await fetch(`${GH}/repos/${owner}/${repo}`, { headers: auth });
        const text = await r.text();
        return new Response(text, { status: r.status, headers: { ...CORS, 'Content-Type': 'application/json; charset=utf-8' } });
      }

      // ---- 触发后台任务 ----
      if (url.pathname === '/gh/dispatch' && request.method === 'POST') {
        const body = await request.json().catch(() => ({}));
        const type = String(body.type || '');
        if (!ALLOWED_TYPES.has(type)) {
          return json({ ok: false, msg: '事件类型不在允许范围内：' + type }, 400);
        }
        const r = await fetch(`${GH}/repos/${owner}/${repo}/dispatches`, {
          method: 'POST',
          headers: { ...auth, 'Content-Type': 'application/json' },
          body: JSON.stringify({ event_type: type, client_payload: body.payload || {} }),
        });
        return json({ ok: r.status === 204, http: r.status });
      }

      // ---- 读取文件 ----
      if (url.pathname === '/gh/file' && request.method === 'GET') {
        const p = url.searchParams.get('path') || '';
        if (!pathAllowed(p)) return json({ ok: false, msg: '路径不允许：' + p }, 400);
        const r = await fetch(`${GH}/repos/${owner}/${repo}/contents/${p}?t=${Date.now()}`, { headers: auth });
        const text = await r.text();
        return new Response(text, { status: r.status, headers: { ...CORS, 'Content-Type': 'application/json; charset=utf-8' } });
      }

      // ---- 写入文件 ----
      if (url.pathname === '/gh/file' && request.method === 'PUT') {
        const body = await request.json().catch(() => ({}));
        if (!pathAllowed(body.path)) return json({ ok: false, msg: '路径不允许' }, 400);
        const r = await fetch(`${GH}/repos/${owner}/${repo}/contents/${body.path}`, {
          method: 'PUT',
          headers: { ...auth, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: body.message || 'update via relay',
            content: body.content,
            sha: body.sha || undefined,
          }),
        });
        const text = await r.text();
        return new Response(text, { status: r.status, headers: { ...CORS, 'Content-Type': 'application/json; charset=utf-8' } });
      }

      return json({ ok: false, msg: '未知接口：' + url.pathname }, 404);
    } catch (e) {
      return json({ ok: false, msg: String(e && e.message || e) }, 500);
    }
  },
};
