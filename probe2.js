// 第二轮：判断 10086 登录态能否续期、是否真的已登录
const fs = require("fs");
const CK = [
  ["c","WRX8xHtxylK0VftHs+9e0bAvIKo/9Lf5FAijXDMerJogaDhZRT3KIwmMfcehh+JH"],
  ["chargeresource","s%3D~e%3D~c%3D~taskId%3D"],
  ["cmccssotoken","WRX8xHtxylK0VftHs+9e0bAvIKo/9Lf5FAijXDMerJogaDhZRT3KIwmMfcehh+JH@.10086.cn"],
  ["CmLocation","731|731"],
  ["CmProvid","hn"],
  ["cvToken","mhrz00ef1dab4f77a05cc5c22b6f78bb"],
  ["defaultloginuser_p","izr73fwOUuimT7R+YElqbvQdIEKrmWCpu49KY4pe7cglQnOlbxDN0nqcpR0yt5wisZCxOLswghEGNJmVqAhv6SMTsRVyT13VInOal6sQlEY+dvBVErR/ksPv5W6XILGzNIChi3gihwmhVzzoGOae/WsG44z9K9sAPKo5vF/bXD2NwSyqpJkEqg/LuT1QHsyO"],
  ["inx","myorders"],
  ["inx2","returnorderqry"],
  ["is_login","true"],
  ["jsessionid-cmcc","n4142D1AB1D9C0F37FA1C855B214E910C-1"],
  ["lgToken","mhrz385c1ac943808c2e423c826c729c"],
  ["sajssdk_2015_cross_new_user","1"],
  ["sendflag","20261021155343958803"],
  ["ssologinprovince","731"],
];
const CKS = CK.map(x => x[0] + "=" + x[1]).join("; ");
const UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

const out = [];

async function req(name, url, withCookie) {
  const r = { name, url, withCookie };
  try {
    const resp = await fetch(url, {
      redirect: "manual",
      headers: Object.assign({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
      }, withCookie ? { Cookie: CKS } : {}),
    });
    r.status = resp.status;
    r.location = resp.headers.get("location") || null;
    const sc = resp.headers.get("set-cookie");
    r.setCookie = sc ? String(sc).slice(0, 300) : null;
    const body = await resp.text();
    r.len = body.length;
    r.phone = (body.match(/1\d{2}\*{3,4}\d{4}/g) || []).slice(0, 3);
    r.isLoginJs = (body.match(/is_login["':=\s]{1,6}(true|false|"true"|"false")/gi) || []).slice(0, 2);
    r.hasLogout = body.includes("退出");
    r.title = (body.match(/<title>([^<]{0,80})<\/title>/) || [])[1] || null;
    r.snippet = (body.match(/欢迎您[^<]{0,40}/g) || []).slice(0, 2);
  } catch (e) {
    r.error = String(e.message || e).slice(0, 100);
  }
  return r;
}

(async () => {
  const T = [
    ["商城个人中心(带cookie)", "https://shop.10086.cn/i/", true],
    ["商城个人中心(无cookie)", "https://shop.10086.cn/i/", false],
    ["商城我的订单(带cookie)", "https://shop.10086.cn/i/?f=myorders", true],
    ["业务查询退订(带cookie)", "https://shop.10086.cn/i/?f=businessquery", true],
  ];
  for (const [n, u, w] of T) {
    const r = await req(n, u, w);
    out.push(r);
    console.log("=== " + n);
    console.log("  status=" + r.status + " len=" + r.len + " loc=" + (r.location || "-"));
    console.log("  title=" + (r.title || "-"));
    console.log("  Set-Cookie: " + (r.setCookie || "(无)"));
    if (r.phone && r.phone.length) console.log("  号码: " + r.phone.join(","));
    if (r.snippet && r.snippet.length) console.log("  欢迎语: " + r.snippet.join(" | "));
    if (r.isLoginJs && r.isLoginJs.length) console.log("  is_login: " + r.isLoginJs.join(","));
    console.log("  含'退出'=" + r.hasLogout);
    if (r.error) console.log("  ERROR: " + r.error);
    console.log("");
  }
  fs.writeFileSync("probe2.txt", JSON.stringify(out, null, 1));
})();
