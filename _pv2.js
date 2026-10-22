const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const b = await chromium.launch({args:['--no-sandbox']});
  const p = await b.newPage({viewport:{width:420,height:900}, deviceScaleFactor:2});
  const errs=[]; p.on('pageerror',e=>errs.push('PAGEERROR '+e.message));
  p.on('console',m=>{ if(m.type()==='error') errs.push('CONSOLE '+m.text().slice(0,160)); });
  await p.goto('https://woshiyigemanhuajia.github.io/hunan-tariff-site/net.html',{waitUntil:'load',timeout:60000});
  await p.waitForTimeout(1500);

  console.log('=== 顶部统计 ===');
  console.log('在线:', await p.locator('#s_online').innerText(),
              '| 平均:', await p.locator('#s_avg').innerText(),
              '| 网络:', await p.locator('#s_net').innerText(),
              '| IP:', await p.locator('#myip').innerText());

  await p.click('#btn_run');
  let waited=0;
  while(waited<150000){
    const t=(await p.locator('#btn_run').innerText()).trim();
    if(t.indexOf('诊断中')<0) break;
    await p.waitForTimeout(2000); waited+=2000;
  }
  console.log('\n=== 扫描耗时', waited/1000, 's ===');

  await p.click('.tab[data-p="p2"]'); await p.waitForTimeout(500);
  console.log('\n=== 站点网格 ===');
  console.log((await p.locator('#grid').innerText()).replace(/\n{2,}/g,'\n'));
  await p.screenshot({path:'/tmp/s_grid.png', fullPage:true});

  await p.click('.tab[data-p="p3"]'); await p.waitForTimeout(400);
  console.log('\n=== 网络评估 ===');
  console.log(await p.locator('#verdict').innerText());

  await p.click('.tab[data-p="p1"]'); await p.waitForTimeout(300);
  await p.selectOption('#target','baidu');
  await p.click('#btn_deep');
  let w2=0;
  while(w2<60000){
    const t=await p.locator('#deep').innerText();
    if(t.indexOf('诊断中')<0 && t.length>40) break;
    await p.waitForTimeout(1500); w2+=1500;
  }
  console.log('\n=== 深度诊断（百度）===');
  console.log(await p.locator('#deep').innerText());
  console.log('分段色块:', JSON.stringify(await p.locator('#deep .seg').allTextContents()));

  await p.click('#btn_dns'); await p.waitForTimeout(12000);
  console.log('\n=== DNS 对比 ===');
  console.log(await p.locator('#dnsout').innerText());

  await p.click('#btn_speed'); await p.waitForTimeout(14000);
  console.log('\n=== 带宽测速 ===');
  console.log(await p.locator('#spout').innerText());

  await p.screenshot({path:'/tmp/s_deep.png', fullPage:true});
  console.log('\n=== JS 错误 ===', errs.length?JSON.stringify(errs.slice(0,8)):'无');
  await b.close();
})().catch(e=>{ console.log('FATAL', e.message); process.exit(1); });
