// 探测给定 10086 cookie 是否仍维持登录态
const fs = require("fs");
const COOKIES = JSON.parse(fs.readFileSync("./ck10086.json", "utf8"));

function cookieHeader(host) {
  const set = COOKIES.filter(c => {
    const d = String(c.domain).replace(/^\./, "");
    return host === d || host.endsWith("." + d);
  });
  return set.map(c => c.name + "=" + c.value).join("; ");
}

const UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

const TARGETS = [
  { name: "10086首页",   url: "https://www.10086.cn/",        host: "www.10086.cn" },
  { name: "商城个人中心", url: "https://shop.10086.cn/i/",     host: "shop.10086.cn" },
  { name: "商城首页",     url: "https://shop.10086.cn/",       host: "shop.10086.cn" },
  { name: "湖南移动",     url: "https://hn.10086.cn/",         host: "hn.10086.cn" },
];

const YES = ["退出登录", "退出登陆", "我的移动", "个人中心", "欢迎您", "已登录", "我的账户", "我的订单"];
const NO  = ["请登录", "登录/注册", "立即登录", "短信登录", "密码登录", "未登录"];

async function probe(t) {
  const ck = cookieHeader(t.host);
  const r = { name: t.name, url: t.url, cookieCount: ck ? ck.split("; ").length : 0, status: null, len: 0, verdict: "未知", sample: "" };
  try {
    const resp = await fetch(t.url, {
      method: "GET",
      redirect: "follow",
      headers: {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cookie": ck,
      },
    });
    r.status = resp.status;
    const body = await resp.text();
    r.len = body.length;
    const hitY = YES.filter(k => body.includes(k));
    const hitN = NO.filter(k => body.includes(k));
    r.hitLoginWords = hitY;
    r.hitGuestWords = hitN;
    if (hitY.length && !hitN.length) r.verdict = "已登录";
    else if (hitN.length && !hitY.length) r.verdict = "未登录(登录态失效)";
    else if (hitY.length && hitN.length) r.verdict = "两者都有(页面含通用登录入口，需人工判)";
    else r.verdict = "无标志";
    // 抓可能的手机号脱敏 1xx****xxxx
    const m = body.match(/1\d{2}\*{4}\d{4}/g);
    if (m) r.phoneLike = [...new Set(m)].slice(0, 5);
    r.sample = body.slice(0, 300);
  } catch (e) {
    r.error = String(e.message || e).slice(0, 120);
  }
  return r;
}

(async () => {
  const out = [];
  for (const t of TARGETS) {
    const r = await probe(t);
    out.push(r);
    console.log("=== " + t.name);
    console.log("  status=" + r.status + " len=" + r.len + " cookies=" + r.cookieCount);
    console.log("  判定: " + r.verdict);
    if (r.hitLoginWords && r.hitLoginWords.length) console.log("  登录标志: " + r.hitLoginWords.join(","));
    if (r.hitGuestWords && r.hitGuestWords.length) console.log("  游客标志: " + r.hitGuestWords.join(","));
    if (r.phoneLike) console.log("  疑似号码: " + r.phoneLike.join(","));
    if (r.error) console.log("  ERROR: " + r.error);
    console.log("");
  }
  fs.writeFileSync("probe10086.txt", JSON.stringify(out, null, 1));
  console.log("写盘 probe10086.txt");
})();
