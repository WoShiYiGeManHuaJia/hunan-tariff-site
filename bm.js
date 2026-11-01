// 云盘取令牌书签脚本 v3（弹窗 + 自动复制版）
// 在 yun.139.com 页面上下文执行，抓到令牌后：
//   ① 自动复制进剪贴板
//   ② 弹出浮层，显示令牌全文 + 「复制」按钮（不自动跳转，避免浮层丢失）
//   ③ 浮层上提供「打开托管页」按钮，带令牌跳回
//
// 抓取策略（三级）：
//   ① 静态扫描：localStorage / sessionStorage / cookie / 页面内联 JSON
//   ② 网络 hook：拦截 XHR + fetch 的 Authorization 头（令牌只在内存时也抓得到）
//   ③ 抓不到不放弃：继续监听 8 秒，期间点一下云盘里任意列表即可捕获
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
  if (!BACK) BACK = 'https://hnvip.pages.dev/token.html';

  // ---------- 工具 ----------
  function copyText(t) {
    // 优先 Clipboard API，失败回退 textarea + execCommand
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t);
        return true;
      }
    } catch (e) {}
    try {
      var ta = document.createElement('textarea');
      ta.value = t;
      ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
      document.body.appendChild(ta);
      ta.focus(); ta.select(); ta.setSelectionRange(0, t.length);
      var ok = document.execCommand('copy');
      try { ta.parentNode.removeChild(ta); } catch (e2) {}
      return ok;
    } catch (e) { return false; }
  }

  function info(t) {
    // 解析出号码（脱敏）与剩余天数，纯展示用
    var out = { phone: '', days: null, prefix: '' };
    try {
      var plain = t;
      if (/^[A-Za-z0-9+/]+={0,2}$/.test(t) && t.length % 4 === 0) {
        try { plain = atob(t.replace(/^\s*Basic\s+/i, '')); } catch (e) {}
      }
      var seg = plain.split(':');
      out.prefix = (seg[0] || '').trim();
      var ph = (seg[1] || '').trim();
      out.phone = ph.length > 7 ? ph.slice(0, 3) + '****' + ph.slice(-4) : ph;
      var pipes = plain.split('|');
      if (pipes.length >= 4) {
        var exp = parseInt(pipes[3], 10);
        if (exp > 0) out.days = Math.round((exp - Date.now()) / 86400000 * 10) / 10;
      }
    } catch (e) {}
    return out;
  }

  function el(html) {
    var d = document.createElement('div');
    d.innerHTML = html;
    return d.firstElementChild;
  }

  // ---------- 成功浮层 ----------
  function showPanel(list) {
    var best = list[0];
    var inf = info(best.t);
    var copied = copyText(best.t);

    var others = '';
    if (list.length > 1) {
      var opts = '';
      for (var i = 0; i < list.length && i < 8; i++) {
        var it = list[i], ii = info(it.t);
        opts += '<option value="' + i + '">' + (ii.prefix || '?') + ' · ' + (ii.phone || '?') +
          (ii.days != null ? ' · 剩 ' + ii.days + '天' : '') + ' · 来自 ' + it.s + '</option>';
      }
      others = '<div style="margin-top:12px">' +
        '<div style="font-size:12px;color:#666;margin-bottom:4px">抓到 ' + list.length + ' 个，可切换：</div>' +
        '<select id="BMSEL" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:8px;font-size:13px;background:#fff">' +
        opts + '</select></div>';
    }

    var panel = el(
      '<div id="BMPANEL" style="position:fixed;inset:0;z-index:2147483646;background:rgba(0,0,0,.45);' +
      'display:flex;align-items:flex-end;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,sans-serif">' +
      '<div style="background:#fff;width:100%;max-width:520px;border-radius:16px 16px 0 0;padding:18px 16px 22px;' +
      'box-shadow:0 -8px 32px rgba(0,0,0,.2);max-height:86vh;overflow:auto">' +

      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">' +
      '<span style="width:26px;height:26px;border-radius:50%;background:#16a34a;color:#fff;' +
      'display:inline-flex;align-items:center;justify-content:center;font-size:16px">✓</span>' +
      '<b style="font-size:17px;color:#111">已抓到令牌</b></div>' +

      '<div id="BMINFO" style="font-size:13px;color:#555;margin-bottom:10px">' +
      (inf.prefix ? '类型 ' + inf.prefix.toUpperCase() : '') +
      (inf.phone ? ' · 号码 ' + inf.phone : '') +
      (inf.days != null ? ' · 剩余 ' + inf.days + ' 天' : '') +
      '</div>' +

      '<textarea id="BMTOK" readonly style="width:100%;height:110px;box-sizing:border-box;' +
      'font:12px/1.6 ui-monospace,Menlo,Consolas,monospace;word-break:break-all;' +
      'border:1px solid #ddd;border-radius:10px;padding:10px;background:#f6f8fa;color:#111;resize:none">' +
      String(best.t).replace(/</g, '&lt;') + '</textarea>' +

      others +

      '<div style="display:flex;gap:10px;margin-top:14px">' +
      '<button id="BMCOPY" style="flex:1;padding:13px;background:#1677ff;color:#fff;border:0;' +
      'border-radius:10px;font-size:16px;font-weight:600">' + (copied ? '已自动复制 · 再点一次' : '复制令牌') + '</button>' +
      '<button id="BMGO" style="flex:1;padding:13px;background:#f0f2f5;color:#111;border:0;' +
      'border-radius:10px;font-size:16px">打开托管页</button>' +
      '</div>' +
      '<button id="BMCLOSE" style="width:100%;margin-top:10px;padding:10px;background:transparent;' +
      'color:#888;border:0;font-size:14px">关闭</button>' +
      '</div></div>'
    );
    document.body.appendChild(panel);

    var cur = best.t;
    var tokBox = panel.querySelector('#BMTOK');
    var infoBox = panel.querySelector('#BMINFO');
    var copyBtn = panel.querySelector('#BMCOPY');

    copyBtn.onclick = function () {
      var ok = copyText(cur);
      copyBtn.textContent = ok ? '✓ 已复制' : '复制失败，请长按选中';
      setTimeout(function () { copyBtn.textContent = '复制令牌'; }, 1600);
    };
    panel.querySelector('#BMCLOSE').onclick = function () {
      try { panel.parentNode.removeChild(panel); } catch (e) {}
    };
    panel.querySelector('#BMGO').onclick = function () {
      location.href = BACK + '#tok=' + encodeURIComponent(cur);
    };
    var sel = panel.querySelector('#BMSEL');
    if (sel) {
      sel.onchange = function () {
        var it = list[parseInt(sel.value, 10)];
        cur = it.t;
        tokBox.textContent = it.t;
        var ii = info(it.t);
        infoBox.textContent = (ii.prefix ? '类型 ' + ii.prefix.toUpperCase() : '') +
          (ii.phone ? ' · 号码 ' + ii.phone : '') +
          (ii.days != null ? ' · 剩余 ' + ii.days + ' 天' : '');
        copyText(it.t);
        copyBtn.textContent = '✓ 已复制新的';
        setTimeout(function () { copyBtn.textContent = '复制令牌'; }, 1600);
      };
    }
  }

  function showDiag() {
    var txt = '域名: ' + location.host + '\nURL: ' + location.href + '\n' +
      '找到令牌: ' + F.length + ' 个\n网络hook: ' + (HOOKED ? '已启用' : '未启用') + '\n' +
      '存储项 ' + K.length + ' 个\n\n' + K.join('\n');
    copyText(txt);
    var panel = el(
      '<div id="BMDIAG" style="position:fixed;inset:0;z-index:2147483646;background:rgba(0,0,0,.45);' +
      'display:flex;align-items:flex-end;justify-content:center;font-family:-apple-system,sans-serif">' +
      '<div style="background:#fff;width:100%;max-width:520px;border-radius:16px 16px 0 0;padding:18px 16px 22px;' +
      'max-height:86vh;overflow:auto">' +
      '<h3 style="color:#c0392b;margin:0 0 8px;font-size:17px">未找到令牌</h3>' +
      '<p style="color:#555;font-size:13px;line-height:1.7;margin:0 0 10px">' +
      '域名 <b>' + location.host + '</b> 下共 ' + K.length + ' 项存储，已复制诊断信息。' +
      '确认已登录云盘；若刚登录，<b>点一下文件列表让它发一次请求</b>再点书签。</p>' +
      '<pre id="DGT" style="white-space:pre-wrap;word-break:break-all;background:#f6f8fa;padding:12px;' +
      'border-radius:8px;font-size:11px;margin:0 0 12px;max-height:240px;overflow:auto">' +
      txt.replace(/</g, '&lt;') + '</pre>' +
      '<div style="display:flex;gap:10px">' +
      '<button id="DGC" style="flex:1;padding:13px;background:#1677ff;color:#fff;border:0;border-radius:10px;font-size:16px">复制诊断信息</button>' +
      '<button id="DGK" style="flex:1;padding:13px;background:#f0f2f5;color:#111;border:0;border-radius:10px;font-size:16px">关闭</button>' +
      '</div></div></div>'
    );
    document.body.appendChild(panel);
    panel.querySelector('#DGC').onclick = function () {
      var ok = copyText(panel.querySelector('#DGT').textContent);
      this.textContent = ok ? '✓ 已复制' : '请长按选中';
    };
    panel.querySelector('#DGK').onclick = function () {
      try { panel.parentNode.removeChild(panel); } catch (e) {}
    };
  }

  function toast(msg) {
    try {
      var d = document.createElement('div');
      d.textContent = msg;
      d.style.cssText = 'position:fixed;left:12px;right:12px;bottom:18px;z-index:2147483645;' +
        'background:#1677ff;color:#fff;font:14px/1.5 -apple-system,sans-serif;padding:12px 14px;' +
        'border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.25)';
      document.body.appendChild(d);
      return d;
    } catch (e) { return null; }
  }

  function finish() {
    if (DONE) return; DONE = true;
    if (F.length) {
      F.sort(function (a, b) {
        var d = rank(a.t) - rank(b.t);
        if (d) return d;
        return b.t.length - a.t.length;
      });
      showPanel(F);
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
      if (tip) { try { tip.parentNode.removeChild(tip); } catch (e) {} }
      setTimeout(finish, 200);
    } else if (waited >= 8000) {
      clearInterval(timer);
      if (tip) { try { tip.parentNode.removeChild(tip); } catch (e) {} }
      finish();
    }
  }, 500);
})();
