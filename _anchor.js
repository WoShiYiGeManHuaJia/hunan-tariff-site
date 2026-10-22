const { chromium } = require('playwright');
const URLS = [
 "https://cdn.jsdelivr.net/npm/vue@3.4.0/dist/vue.global.prod.js",
 "https://cdn.jsdelivr.net/npm/typescript@5.4.5/lib/typescript.js",
 "https://1.1.1.1/cdn-cgi/trace",
 "https://cloudflare.com/cdn-cgi/trace",
 "https://www.google.com/generate_204",
 "https://ajax.googleapis.com/ajax/libs/jquery/3.7.1/jquery.min.js",
 "https://unpkg.com/vue@3.4.0/dist/vue.global.prod.js",
 "https://registry.npmmirror.com/vue/latest",
 "https://www.baidu.com/favicon.ico",
 "https://static.cloudflareinsights.com/beacon.min.js",
 "https://fastly.jsdelivr.net/npm/vue@3.4.0/dist/vue.global.prod.js",
 "https://img.alicdn.com/tfs/TB1.gif"
];
(async () => {
  const b = await chromium.launch({args:['--no-sandbox']});
  const p = await b.newPage();
  await p.goto('https://woshiyigemanhuajia.github.io/hunan-tariff-site/net.html',{waitUntil:'load',timeout:60000});
  const out = await p.evaluate(async (URLS)=>{
    const res=[];
    for(const u of URLS){
      const t0=performance.now();
      let err=null;
      try{ await fetch(u+'?_a='+Date.now(),{cache:'no-store',mode:'no-cors',credentials:'omit'}); }
      catch(e){ err=String(e.message); }
      await new Promise(r=>setTimeout(r,400));
      const all=performance.getEntriesByType('resource').filter(e=>e.name.indexOf(u)===0 && e.startTime>t0-20);
      const e=all[all.length-1];
      res.push({u, err, has:!!e,
        dns: e?Math.round(e.domainLookupEnd-e.domainLookupStart):null,
        tcp: e?Math.round(e.connectEnd-e.connectStart):null,
        ttfb: e&&e.responseStart?Math.round(e.responseStart-e.startTime):null,
        dur: e?Math.round(e.duration):null,
        transfer: e?e.transferSize:null});
    }
    return res;
  }, URLS);
  console.log(JSON.stringify(out,null,1));
  await b.close();
})().catch(e=>{console.log('FATAL',e.message);process.exit(1);});
