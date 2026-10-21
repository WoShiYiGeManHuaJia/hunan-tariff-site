const fs = require("fs");
const CK = [
  ["c","WRX8xHtxylK0VftHs+9e0bAvIKo/9Lf5FAijXDMerJogaDhZRT3KIwmMfcehh+JH",".10086.cn","/"],
  ["cmccssotoken","WRX8xHtxylK0VftHs+9e0bAvIKo/9Lf5FAijXDMerJogaDhZRT3KIwmMfcehh+JH@.10086.cn",".10086.cn","/"],
  ["CmLocation","731|731",".10086.cn","/"],
  ["CmProvid","hn",".10086.cn","/"],
  ["cvToken","mhrz00ef1dab4f77a05cc5c22b6f78bb",".10086.cn","/"],
  ["defaultloginuser_p","izr73fwOUuimT7R+YElqbvQdIEKrmWCpu49KY4pe7cglQnOlbxDN0nqcpR0yt5wisZCxOLswghEGNJmVqAhv6SMTsRVyT13VInOal6sQlEY+dvBVErR/ksPv5W6XILGzNIChi3gihwmhVzzoGOae/WsG44z9K9sAPKo5vF/bXD2NwSyqpJkEqg/LuT1QHsyO",".10086.cn","/"],
  ["is_login","true",".10086.cn","/"],
  ["jsessionid-cmcc","n4142D1AB1D9C0F37FA1C855B214E910C-1",".10086.cn","/"],
  ["lgToken","mhrz385c1ac943808c2e423c826c729c",".10086.cn","/"],
  ["sendflag","20261021155343958803",".10086.cn","/"],
  ["chargeresource","s%3D~e%3D~c%3D~taskId%3D","shop.10086.cn","/"],
  ["inx","myorders","shop.10086.cn","/i"],
  ["inx2","returnorderqry","shop.10086.cn","/i"],
  ["ssologinprovince","731","shop.10086.cn","/i"],
];
const MUA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const out = [];

async function main() {
  let chromium = null;
  try { chromium = require("playwright").chromium; } catch (e) {
    console.log("playwright 未安装"); return;
  }
  const browser = await chromium.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  const ctx = await browser.newContext({ userAgent: MUA, viewport: { width: 390, height: 844 }, locale: "zh-CN", timezoneId: "Asia/Shanghai" });
  await ctx.addCookies(CK.map(([name, value, domain, path]) => ({
    name, value, domain, path,
    httpOnly: ["cmccssotoken", "jsessionid-cmcc", "sendflag", "ssologinprovince"].includes(name),
    secure: true, sameSite: "Lax",
  })));
  const page = await ctx.newPage();
  const pages = [
    ["商城个人中心", "https://shop.10086.cn/i/"],
    ["移动官网", "https://www.10086.cn/"],
  ];
  for (const [name, url] of pages) {
    const r = { name, url };
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(6000);
      const txt = await page.evaluate(() => document.body.innerText.slice(0, 1200));
      const html = await page.content();
      r.text = txt;
      r.phone = [...new Set((txt.match(/1\d{2}\*{3,4}\d{4}/g) || []))].slice(0, 3);
      r.hasLogout = txt.includes("退出");
      const loginBtn = /登录|登陆/.test(txt);
      r.loginBtn = loginBtn;
      r.cookiesNow = (await ctx.cookies()).map(c => c.name).join(",");
    } catch (e) {
      r.error = String(e.message || e).slice(0, 120);
    }
    out.push(r);
    console.log("=== " + name);
    console.log("  号码: " + (r.phone && r.phone.length ? r.phone.join(",") : "(无)"));
    console.log("  含'退出'=" + r.hasLogout + "  含'登录'按钮=" + r.loginBtn);
    console.log("  当前cookie: " + (r.cookiesNow || "-"));
    console.log("  正文片段: " + String(r.text || r.error || "").replace(/\n+/g, " / ").slice(0, 400));
    console.log("");
  }
  await browser.close();
  fs.writeFileSync("probe3.txt", JSON.stringify(out, null, 1));
}
main().catch(e => { console.log("FATAL", String(e.message || e).slice(0, 200)); });
