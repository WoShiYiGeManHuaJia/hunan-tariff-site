// 云盘取令牌书签脚本 v2（增强版）
// ① 扫 localStorage / sessionStorage / cookie / 页面内联 JSON
// ② hook XHR + fetch，捕获随请求下发的 Authorization（令牌只在内存时也抓得到）
// ③ 抓不到不立刻放弃：继续监听 8 秒，期间点一下云盘里任意列表即可捕获
(function () {
  var F = [], K = [], DONE = false, HOOKED = false;
  var P = /(?:pc|app|h5|android|ios|web|wap|pad|win|mac):1\d{10}:[A-Za-z0-9|._\-]+/gi;
  var PRI = { pc: 0, app: 1, h5: 2, web: 3, wap: 4, android: 5, ios: 6, pad: 7, win: 8, mac: 9 };

  function rank(t) {
    var c = (t.split(':')[0] || '').toLowerCase();
    var r = PRI[c];
    return (r === undefined ? 50 : r);
  }
  function add(t, s) {
    if (!t) return;
    for (var i = 0; i < F.length; i++) if (F[i].t === t) return;
    F.push({ s: s, t: t });
  }
  function norm(v) {
    var out = [v], i, d;
    var bp = String(v).replace(/^\s*Basic\s+/i, '');
    if (bp !== v) out.push(bp);
    var n = out.length;
    for (i = 0; i < n; i++) { try { d = atob(out[i]); if (d) out.push(d); } catch (e) {} }
    return out;
  }
  function look(v, tag) {
    if (typeof v !== 'string' || !v) return;
    var cs = norm(v), i, j, m;
    for (i = 0; i < cs.length; i++) {
      m = cs[i].match(P);
      if (m) for (j = 0; j < m.length; j++) add(m[j], tag);
    }
    var pv = v.length > 30 ? (v.slice(0, 18) + '…(' + v.length + ')') : v;
    K.push(tag + ' | ' + pv);
  }
  function deepLook(o, tag, dep) {
    if (dep > 4 || o == null) return;
    if (typeof o === 'string') { look(o, tag); return; }
    if (typeof o !== 'object') return;
    try {
      for (var k in o) {
        var v = o[k];
        if (typeof v === 'string') look(v, tag + '.' + k);
        else deepLook(v, tag + '.' + k, dep + 1);
      }
    } catch (e) {}
  }

  // ---------- ① 静态扫描 ----------
  try { for (var i = 0; i < localStorage.length; i++) { var k1 = localStorage.key(i); look(localStorage.getItem(k1), 'LS.' + k1); } } catch (e) { K.push('LS失败:' + e.message); }
  try { for (var j = 0; j < sessionStorage.length; j++) { var k2 = sessionStorage.key(j); look(sessionStorage.getItem(k2), 'SS.' + k2); } } catch (e) { K.push('SS失败:' + e.message); }
  var ck = document.cookie || '';
  ck.split(';').forEach(function (p) {
    var t = p.trim(); if (!t) return;
    var i = t.indexOf('='); if (i < 0) return;
    var n = t.slice(0, i), v = t.slice(i + 1);
    try { v = decodeURIComponent(v); } catch (e) {}
    look(v, 'CK.' + n);
  });
  // 页面内联 JSON / 全局变量
  try {
    var sc = document.querySelectorAll('script');
    for (var s = 0; s < sc.length; s++) {
      var tx = sc[s].textContent || '';
      if (tx.length > 20 && tx.length < 400000) look(tx, 'SCRIPT#' + s);
    }
  } catch (e) {}
  try {
    var G = ['__INITIAL_STATE__', '__NEXT_DATA__', '__NUXT__', 'ACCOUNT_INFO', 'userInfo', 'accountInfo', 'auth'];
    for (var g = 0; g < G.length; g++) if (window[G[g]]) deepLook(window[G[g]], 'WIN.' + G[g], 0);
  } catch (e) {}

  // ---------- ② 网络 hook ----------
  try {
    var _sr = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
      try { if (/^authorization$/i.test(k)) look(v, 'XHR.Header'); } catch (e) {}
      return _sr.apply(this, arguments);
    };
    var _f = window.fetch;
    window.fetch = function (input, init) {
      try {
        var h = init && init.headers;
        if (h) {
          if (typeof h.get === 'function') { var a = h.get('Authorization'); if (a) look(a, 'FETCH.Header'); }
          else { for (var kk in h) if (/^authorization$/i.test(kk)) look(h[kk], 'FETCH.Header'); }
        }
        if (input && typeof input.headers !== 'undefined' && input.headers && typeof input.headers.get === 'function') {
          var b = input.headers.get('Authorization'); if (b) look(b, 'FETCH.Req');
        }
      } catch (e) {}
      return _f.apply(this, arguments);
    };
    HOOKED = true;
  } catch (e) { K.push('hook失败:' + e.message); }

  // ---------- 回跳地址 ----------
  var src = (document.currentScript && document.currentScript.src) || '';
  var BACK = '';
  try { BACK = decodeURIComponent((src.split('#back=')[1] || '')); } catch (e) {}
  if (!BACK) BACK = 'https://hnvip.pages.dev/manage.html';

  function toast(msg) {
    try {
      var d = document.createElement('div');
      d.textContent = msg;
      d.style.cssText = 'position:fixed;left:12px;right:12px;bottom:18px;z-index:2147483647;background:#1677ff;color:#fff;font:14px/1.5 -apple-system,sans-serif;padding:12px 14px;border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.25)';
      document.body.appendChild(d);
      return d;
    } catch (e) { return null; }
  }

  function showDiag() {
    var txt = '域名: ' + location.host + '\nURL: ' + location.href + '\n' +
      '找到令牌: ' + F.length + ' 个\n网络hook: ' + (HOOKED ? '已启用' : '未启用') + '\n' +
      '存储项 ' + K.length + ' 个\n\n' + K.join('\n');
    try { navigator.clipboard.writeText(txt); } catch (e) {}
    try {
      document.open();
      document.write(
        '<meta name="viewport" content="width=device-width,initial-scale=1">' +
        '<body style="font:13px/1.7 -apple-system,sans-serif;padding:16px;background:#fff">' +
        '<h3 style="color:#c0392b;margin:0 0 8px">未找到令牌</h3>' +
        '<p style="color:#555">域名 <b>' + location.host + '</b> 下共 ' + K.length + ' 项存储。' +
        '已复制到剪贴板，把这段发我即可定位。</p>' +
        '<p style="color:#666;font-size:12px">提示：确认已登录云盘；若刚登录，' +
        '<b>点一下文件列表让它发一次请求</b>再点书签。</p>' +
        '<pre id="DG" style="white-space:pre-wrap;word-break:break-all;background:#f6f8fa;padding:12px;border-radius:8px;font-size:12px;margin:10px 0">' +
        txt.replace(/</g, '&lt;') + '</pre>' +
        '<button onclick="var t=document.getElementById(\'DG\').textContent;navigator.clipboard.writeText(t);this.textContent=\'已复制\'" ' +
        'style="padding:10px 16px;background:#1677ff;color:#fff;border:0;border-radius:8px;font-size:15px">复制诊断信息</button>');
      document.close();
    } catch (e) { alert(txt); }
  }

  function finish() {
    if (DONE) return; DONE = true;
    if (F.length) {
      F.sort(function (a, b) {
        var d = rank(a.t) - rank(b.t);
        if (d) return d;
        return b.t.length - a.t.length;
      });
      var best = F[0];
      try { navigator.clipboard.writeText(best.t); } catch (e) {}
      location.href = BACK + '#tok=' + encodeURIComponent(best.t);
      return;
    }
    showDiag();
  }

  if (F.length) { finish(); return; }

  // ---------- ③ 抓不到 → 监听 8 秒 ----------
  var tip = toast('未直接找到令牌，正在监听 8 秒…请点一下云盘里的文件/列表');
  var waited = 0;
  var timer = setInterval(function () {
    waited += 500;
    if (F.length) {
      clearInterval(timer);
      if (tip) tip.textContent = '✓ 抓到令牌，正在跳回…';
      setTimeout(finish, 300);
    } else if (waited >= 8000) {
      clearInterval(timer);
      if (tip) { try { tip.parentNode.removeChild(tip); } catch (e) {} }
      finish();
    }
  }, 500);
})();
