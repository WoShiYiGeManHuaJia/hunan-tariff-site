const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({args:['--no-sandbox']});
  const p = await b.newPage();
  await p.goto('https://woshiyigemanhuajia.github.io/hunan-tariff-site/net.html',{waitUntil:'load',timeout:60000});
  await p.waitForTimeout(1000);
  const out = await p.evaluate(async ()=>{
    const res={};
    res.bufSize = (performance.setResourceTimingBufferSize)?'api-ok':'no-api';
    res.entriesBefore = performance.getEntriesByType('resource').length;
    const a = await probeAnchor();
    res.anchor = a ? {name:a.anchorName, ok:a.ok, dns:a.dns, tcp:a.tcp, ttfb:a.ttfb, total:a.total, via:a.via, err:a.err||null} : null;
    try{ performance.clearResourceTimings(); }catch(e){}
    const t0=performance.now();
    try{ await fetch("https://img.alicdn.com/tfs/TB1.gif?x="+Date.now(),{cache:'no-store',mode:'no-cors',credentials:'omit'}); }
    catch(e){ res.manualErr=String(e.message); }
    await new Promise(r=>setTimeout(r,600));
    res.manualEntries = performance.getEntriesByType('resource').map(e=>({n:e.name.slice(0,58),
      dns:Math.round(e.domainLookupEnd-e.domainLookupStart), tcp:Math.round(e.connectEnd-e.connectStart),
      rs:Math.round(e.responseStart), dur:Math.round(e.duration)}));
    res.logText = document.getElementById('log').innerText.split('\n').slice(-6).join(' | ');
    return res;
  });
  console.log(JSON.stringify(out,null,1));
  await b.close();
})().catch(e=>{console.log('FATAL',e.message);process.exit(1);});
