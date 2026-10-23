// 云盘取令牌书签脚本（短版书签会加载本文件）
// 用法：在 yun.139.com 登录后点书签，本脚本扫描 localStorage/sessionStorage/cookie，
// 找到 pc:手机号:token 形式的令牌后跳回管理页。
(function () {
  try {
    var F = [], K = [], P = /pc:1\d{10}:[A-Za-z0-9|._-]+/;
    function add(t, s) { for (var i = 0; i < F.length; i++) if (F[i].t === t) return; F.push({ s: s, t: t }); }
    function look(v, tag) {
      if (typeof v !== 'string' || !v) return;
      // authorization 可能是 "Basic <base64>"，先剥前缀再解码
      var c = [v], i, d;
      var bp = v.replace(/^\s*Basic\s+/i, '');
      if (bp !== v) c.push(bp);
      var n0 = c.length;
      for (i = 0; i < n0; i++) { try { d = atob(c[i]); if (d) c.push(d); } catch (e) {} }
      for (i = 0; i < c.length; i++) { var m = c[i].match(P); if (m) add(m[0], tag); }
      var pv = v.length > 28 ? (v.slice(0, 16) + '…(' + v.length + ')') : v;
      K.push(tag + ' | ' + pv);
    }
    try { for (var i = 0; i < localStorage.length; i++) { var k = localStorage.key(i); look(localStorage.getItem(k), 'LS.' + k); } } catch (e) { K.push('LS读取失败:' + e.message); }
    try { for (var j = 0; j < sessionStorage.length; j++) { var k2 = sessionStorage.key(j); look(sessionStorage.getItem(k2), 'SS.' + k2); } } catch (e) { K.push('SS读取失败:' + e.message); }
    var ck = document.cookie || '';
    ck.split(';').forEach(function (p) {
      var t = p.trim(); if (!t) return;
      var i = t.indexOf('='); if (i < 0) return;
      var n = t.slice(0, i), v = t.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) {}
      look(v, 'CK.' + n);
    });

    // 回跳地址：从脚本 URL 的 #back= 取，取不到用默认
    var src = (document.currentScript && document.currentScript.src) || '';
    var BACK = '';
    try { BACK = decodeURIComponent((src.split('#back=')[1] || '')); } catch (e) {}
    if (!BACK) BACK = 'https://woshiyigemanhuajia.github.io/hunan-tariff-site/manage.html';

    if (F.length) {
      var best = F[0];
      for (var i2 = 0; i2 < F.length; i2++) if (F[i2].t.length > best.t.length) best = F[i2];
      try { navigator.clipboard.writeText(best.t); } catch (e) {}
      location.href = BACK + '#tok=' + encodeURIComponent(best.t);
      return;
    }

    var txt = '域名: ' + location.host + '\n存储项 ' + K.length + ' 个\n\n' + K.join('\n');
    try { navigator.clipboard.writeText(txt); } catch (e) {}
    document.open();
    document.write(
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<body style="font:13px/1.7 -apple-system,sans-serif;padding:16px;background:#fff">' +
      '<h3 style="color:#c0392b;margin:0 0 8px">未找到令牌</h3>' +
      '<p style="color:#555">域名 <b>' + location.host + '</b> 下共 ' + K.length + ' 项存储，已尝试复制到剪贴板。</p>' +
      '<pre id="DG" style="white-space:pre-wrap;word-break:break-all;background:#f6f8fa;padding:12px;border-radius:8px;font-size:12px;margin:10px 0">' +
      txt.replace(/</g, '&lt;') + '</pre>' +
      '<button onclick="var t=document.getElementById(\'DG\').textContent;navigator.clipboard.writeText(t);this.textContent=\'已复制\'" ' +
      'style="padding:10px 16px;background:#1677ff;color:#fff;border:0;border-radius:8px;font-size:15px">复制诊断信息</button>' +
      '<p style="color:#666;font-size:12px;margin-top:12px">把这段发给我，我据此定位令牌存在哪。</p>');
    document.close();
  } catch (e) {
    alert('读取出错: ' + e.message);
  }
})();