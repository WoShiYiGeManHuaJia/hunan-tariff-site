const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({args:['--no-sandbox']});
  const p = await b.newPage();
  await p.goto('https://woshiyigemanhuajia.github.io/hunan-tariff-site/net.html',{waitUntil:'load',timeout:60000});
  await p.waitForTimeout(1000);
  const out = await p.evaluate(async ()=>{
    const steps=[];
    for(const a of ANCHORS){
      try{ performance.clearResourceTimings(); }catch(e){}
      const r = await probeOnce({id:'anchor',n:a.n,u:a.u,c:''},5000,true);
      steps.push({n:a.n, ok:!!r.ok, via:r.via||null, dns:r.dns, tcp:r.tcp, ttfb:r.ttfb,
        err:r.err||null,
        ents: performance.getEntriesByType('resource').map(e=>e.name.slice(0,46)+' dns'+Math.round(e.domainLookupEnd-e.domainLookupStart)+' tcp'+Math.round(e.connectEnd-e.connectStart))});
    }
    try{ performance.clearResourceTimings(); }catch(e){}
    const A = await probeAnchor();
    return {steps, anchor: A?{name:A.anchorName, dns:A.dns, tcp:A.tcp, ttfb:A.ttfb, wait:A.wait, trans:A.trans}:null};
  });
  console.log(JSON.stringify(out,null,1));
  await b.close();
})().catch(e=>{console.log('FATAL',e.message);process.exit(1);});
