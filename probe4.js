// 探测 10086 老 cookie 是否仍有效（cookie 从环境变量读入，不落盘仓库）
const fs = require("fs");
const RAW = process.env.CK10086 || "";
let COOKIES = [];
try { COOKIES = JSON.parse(RAW); } catch (e) { console.log("cookie 解析失败"); process.exit(1); }

function ckHeader(host) {
  return COOKIES
    .filter(c => { const d = String(c.domain).replace(/^\./, ""); return host === d || host.endsWith("." + d); })
    .map(c => c.name + "=" + c.value).join("; ");
}

const MUA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const UA = MUA;

// 判定：需要登录才会有的内容
const AUTH_MARK = ["退出", "尊敬的用户", "余额", "话费余额", "套餐余量", "我的移动", "已登录", "退出登录"];
// 判定：被踢回登录页
const GUEST_MARK = ["短信随机码", "请输入短信", "随机码登录", "获取验证码", "请登录", "服务密码登录", "登录/注册"];

const out = [];

async function hit(name, url, host, withCk) {
  const r = { name, url, withCk };
  try {
    const resp = await fetch(url, {
      redirect: "follow",
      headers: Object.assign({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://shop.10086.cn/",
      }, withCk ? { Cookie: ckHeader(host) } : {}),
    });
    r.status = resp.status;
    r.finalUrl = resp.url;
    const body = await resp.text();
    r.len = body.length;
    r.title = (body.match(/<title>([^<]{0,60})<\/title>/) || [])[1] || null;
    r.authHit = AUTH_MARK.filter(k => body.includes(k));
    r.guestHit = GUEST_MARK.filter(k => body.includes(k));
    r.phone = [...new Set((body.match(/1\d{2}\*{3,4}\d{4}/g) || []))].slice(0, 3);
    r.verdict = r.authHit.length && !r.guestHit.length ? "有效(已登录)"
      : r.guestHit.length && !r.authHit.length ? "失效(跳登录页)"
      : r.authHit.length && r.guestHit.length ? "两者都有(需看渲染)"
      : "无标志(静态壳)";
    const sc = resp.headers.get("set-cookie");
    r.setCookie = sc ? String(sc).slice(0, 200) : null;
  } catch (e) {
    r.error = String(e.message || e).slice(0, 100);
    r.verdict = "请求失败";
  }
  return r;
}

async function withBrowser() {
  let chromium = null;
  try { chromium = require("playwright").chromium; } catch (e) { return { skipped: "playwright 未装" }; }
  const browser = await chromium.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"] });
  const res = [];
  try {
    const ctx = await browser.newContext({ userAgent: MUA, viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, locale: "zh-CN", timezoneId: "Asia/Shanghai" });
    await ctx.addCookies(COOKIES.filter(c => /\.(10086\.cn)$/.test(c.domain) || c.domain === ".10086.cn" || c.domain === "shop.10086.cn").map(c => ({
      name: c.name, value: c.value,
      domain: c.domain.startsWith(".") ? c.domain : c.domain,
      path: c.path || "/",
      httpOnly: ["cmccssotoken", "jsessionid-cmcc", "sendflag", "ssologinprovince"].includes(c.name),
      secure: true, sameSite: "Lax",
    })));
    const page = await ctx.newPage();
    const targets = [
      ["商城个人中心", "https://shop.10086.cn/i/"],
      ["套餐余量查询", "https://shop.10086.cn/i/?f=packremainqry"],
    ];
    for (const [n, u] of targets) {
      const r = { name: n, url: u };
      try {
        await page.goto(u, { waitUntil: "domcontentloaded", timeout: 45000 });
        await page.waitForTimeout(7000);
        const txt = await page.evaluate(() => document.body.innerText.slice(0, 1500));
        r.text = txt;
        r.phone = [...new Set((txt.match(/1\d{2}\*{3,4}\d{4}/g) || []))].slice(0, 3);
        r.authHit = AUTH_MARK.filter(k => txt.includes(k));
        r.guestHit = GUEST_MARK.filter(k => txt.includes(k));
        r.verdict = r.phone.length || (r.authHit.length && !r.guestHit.length) ? "有效(已登录)"
          : r.guestHit.length ? "失效(跳登录页)" : "无标志";
      } catch (e) { r.error = String(e.message || e).slice(0, 100); r.verdict = "请求失败"; }
      res.push(r);
    }
  } finally { try { await browser.close(); } catch (e) {} }
  return res;
}

(async () => {
  console.log("cookie 条数:", COOKIES.length);
  const T = [
    ["套餐余量(带)", "https://shop.10086.cn/i/?f=packremainqry", "shop.10086.cn", true],
    ["套餐余量(不带)", "https://shop.10086.cn/i/?f=packremainqry", "shop.10086.cn", false],
    ["个人中心(带)", "https://shop.10086.cn/i/", "shop.10086.cn", true],
    ["个人中心(不带)", "https://shop.10086.cn/i/", "shop.10086.cn", false],
    ["商城首页(带)", "https://shop.10086.cn/", "shop.10086.cn", true],
  ];
  for (const [n, u, h, w] of T) {
    const r = await hit(n, u, h, w);
    out.push(r);
    console.log("=== " + n);
    console.log("   status=" + r.status + " len=" + r.len + " 判定=" + r.verdict);
    console.log("   title=" + (r.title || "-"));
    console.log("   finalUrl=" + (r.finalUrl || "-"));
    if (r.phone && r.phone.length) console.log("   号码=" + r.phone.join(","));
    if (r.authHit && r.authHit.length) console.log("   登录标志=" + r.authHit.join(","));
    if (r.guestHit && r.guestHit.length) console.log("   游客标志=" + r.guestHit.join(","));
    console.log("   Set-Cookie=" + (r.setCookie || "(无)"));
    if (r.error) console.log("   ERROR=" + r.error);
    console.log("");
  }
  console.log("──── 浏览器渲染 ────");
  const b = await withBrowser();
  if (b.skipped) console.log(b.skipped);
  else {
    for (const r of b) {
      out.push({ browser: true, ...r });
      console.log("=== [渲染] " + r.name);
      console.log("   判定=" + r.verdict);
      console.log("   号码=" + (r.phone && r.phone.length ? r.phone.join(",") : "(无)"));
      console.log("   登录标志=" + (r.authHit || []).join(",") + " | 游客标志=" + (r.guestHit || []).join(","));
      console.log("   正文=" + String(r.text || r.error || "").replace(/\n+/g, " / ").slice(0, 350));
      console.log("");
    }
  }
  fs.writeFileSync("probe4.txt", JSON.stringify(out, null, 1));
})();
