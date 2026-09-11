/* 四站公共增强：CSV 导出 + 收藏关注 + 深色模式兜底
 * 零侵入设计：不修改各站 app.js，仅由 index.html 引入本文件。
 * 四站共用一份（放在公开仓根目录，子目录站用 ../common-extras.js 引用）。
 */
(function () {
  "use strict";

  var path = location.pathname || "";
  var SITE = /\/unicom\//.test(path) ? "unicom"
    : /\/telecom\//.test(path) ? "telecom"
      : /\/gb\//.test(path) ? "gb" : "mobile";
  var SITE_CN = { mobile: "移动", unicom: "联通", telecom: "电信", gb: "广电" }[SITE];
  var FAV_KEY = "trf_fav_" + SITE;
  var DATA_DIR = "./data/";
  var favOnly = false;

  /* ───────── 收藏存储 ───────── */
  function favAll() {
    try { return JSON.parse(localStorage.getItem(FAV_KEY) || "{}"); } catch (e) { return {}; }
  }
  function favSave(o) {
    try { localStorage.setItem(FAV_KEY, JSON.stringify(o)); } catch (e) { }
  }
  function isFav(name) { return name && !!favAll()[name]; }
  function toggleFav(name) {
    var o = favAll();
    if (o[name]) { delete o[name]; } else { o[name] = 1; }
    favSave(o);
    return !!o[name];
  }
  function favCount() { return Object.keys(favAll()).length; }

  /* ───────── 当前板块判定 ───────── */
  function currentSection() {
    var tab = document.querySelector(".tab.active");
    var view = tab ? (tab.getAttribute("data-view") || "") : "";
    if (view === "quanguo") return "quanguo";
    var sel = document.getElementById("pProv") || document.getElementById("oProv");
    if (sel && sel.value) return sel.value;
    return "hunan";
  }
  function secLabel(sec) {
    var sel = document.getElementById("pProv") || document.getElementById("oProv");
    if (sel && sel.value === sec) {
      var opt = sel.options[sel.selectedIndex];
      if (opt && opt.textContent) return opt.textContent.trim();
    }
    if (sec === "quanguo") return "全网";
    return sec;
  }

  /* ───────── 条目 → 行（适配两种数据结构） ───────── */
  function itemToRow(it) {
    var r = {};
    // 移动站：{name, fields:{...}}
    if (it.fields && typeof it.fields === "object") {
      r["业务名称"] = it.name || "";
      var f = it.fields;
      for (var k in f) {
        if (Object.prototype.hasOwnProperty.call(f, k)) r[k] = f[k];
      }
      return r;
    }
    // 联通/电信/广电：{title, fee, firstLevel, secondLevel, detail:{...}}
    r["业务名称"] = it.title || it.name || "";
    r["资费"] = it.fee || it.feesStandard || "";
    r["一级分类"] = it.firstLevel || "";
    r["二级分类"] = it.secondLevel || "";
    var d = it.detail || {};
    for (var kk in d) {
      if (Object.prototype.hasOwnProperty.call(d, kk) && d[kk] != null &&
        typeof d[kk] !== "object") {
        r[kk] = d[kk];
      }
    }
    return r;
  }

  function csvCell(v) {
    var s = (v == null ? "" : String(v));
    s = s.replace(/\r?\n/g, " ").replace(/"/g, '""');
    return /[",]/.test(s) ? '"' + s + '"' : s;
  }

  function exportCsv() {
    var sec = currentSection();
    var url = DATA_DIR + sec + ".json";
    fetch(url).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      var items = (d && d.items) || [];
      if (!items.length) { alert("该板块暂无数据可导出"); return; }
      var rows = items.map(itemToRow);
      var keys = [];
      rows.forEach(function (r) {
        Object.keys(r).forEach(function (k) { if (keys.indexOf(k) < 0) keys.push(k); });
      });
      var lines = [keys.map(csvCell).join(",")];
      rows.forEach(function (r) {
        lines.push(keys.map(function (k) { return csvCell(r[k]); }).join(","));
      });
      var blob = new Blob(["\ufeff" + lines.join("\r\n")],
        { type: "text/csv;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = SITE_CN + "资费_" + secLabel(sec) + "_" +
        new Date().toISOString().slice(0, 10) + ".csv";
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    }).catch(function (e) {
      alert("导出失败（" + url + "）：" + e.message);
    });
  }

  /* ───────── 收藏星标注入 ───────── */
  function itemName(el) {
    var n = el.querySelector(".item-name");
    if (n) return (n.textContent || "").trim();
    var t = el.querySelector(".item-title, .title, b");
    return t ? (t.textContent || "").trim() : "";
  }

  function decorate(el) {
    if (!el || el.getAttribute("data-ce-done")) return;
    var name = itemName(el);
    if (!name) return;
    el.setAttribute("data-ce-done", "1");
    var head = el.querySelector(".item-head") || el.firstElementChild || el;
    var star = document.createElement("span");
    star.className = "ce-star" + (isFav(name) ? " on" : "");
    star.textContent = isFav(name) ? "★" : "☆";
    star.title = "收藏/取消收藏该资费";
    star.setAttribute("data-ce-star", name);
    star.addEventListener("click", function (ev) {
      ev.stopPropagation();          // 不触发卡片展开
      ev.preventDefault();
      var on = toggleFav(name);
      star.textContent = on ? "★" : "☆";
      star.classList.toggle("on", on);
      if (favOnly) applyFavFilter();
      syncFavBtnText();
    });
    head.appendChild(star);
    if (favOnly && !isFav(name)) el.style.display = "none";
  }

  function decorateAll() {
    var list = document.querySelectorAll(".list .item");
    for (var i = 0; i < list.length; i++) decorate(list[i]);
  }

  function applyFavFilter() {
    var list = document.querySelectorAll(".list .item");
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      var nm = itemName(el);
      el.style.display = (favOnly && !isFav(nm)) ? "none" : "";
    }
    syncFavBtnText();
  }

  function syncFavBtnText() {
    var btns = document.querySelectorAll('[data-ce="fav"]');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      b.textContent = favOnly ? "显示全部" : "只看收藏(" + favCount() + ")";
      b.classList.toggle("ce-on", favOnly);
    }
  }

  /* ───────── 工具栏按钮注入 ───────── */
  function injectToolbar() {
    var bars = document.querySelectorAll(".toolbar");
    for (var i = 0; i < bars.length; i++) {
      var bar = bars[i];
      if (bar.querySelector('[data-ce="csv"]')) continue;

      var csv = document.createElement("button");
      csv.type = "button";
      csv.className = "btn ce-btn";
      csv.setAttribute("data-ce", "csv");
      csv.textContent = "导出CSV";
      csv.title = "导出当前板块全量资费为 CSV（Excel 可直接打开）";
      csv.addEventListener("click", exportCsv);
      bar.appendChild(csv);

      var fav = document.createElement("button");
      fav.type = "button";
      fav.className = "btn ce-btn";
      fav.setAttribute("data-ce", "fav");
      fav.title = "只显示已收藏（★）的资费条目；收藏保存在本机浏览器";
      fav.addEventListener("click", function () {
        favOnly = !favOnly;
        applyFavFilter();
      });
      bar.appendChild(fav);
    }
    syncFavBtnText();
  }

  /* ───────── 深色模式兜底（电信/广电页面若缺按钮则补一个） ───────── */
  function ensureThemeBtn() {
    if (document.getElementById("themeBtn")) return;   // 已有则不动
    var box = document.querySelector(".topbar-actions");
    if (!box) return;
    var btn = document.createElement("button");
    btn.className = "glass-btn";
    btn.id = "themeBtn";
    btn.title = "切换深色/浅色模式";
    btn.textContent = document.body.classList.contains("dark") ? "浅色" : "深色";
    btn.addEventListener("click", function () {
      var dark = !document.body.classList.contains("dark");
      document.body.classList.toggle("dark", dark);
      btn.textContent = dark ? "浅色" : "深色";
      try { localStorage.setItem("trf_dark", dark ? "1" : "0"); } catch (e) { }
    });
    box.appendChild(btn);
  }

  /* ───────── 样式 ───────── */
  function injectStyle() {
    var css = [
      ".ce-btn{margin-left:6px;white-space:nowrap}",
      ".ce-btn.ce-on{background:linear-gradient(120deg,#ffb347,#ff8c1a);color:#fff;border-color:transparent}",
      ".ce-star{margin-left:auto;flex:none;font-size:17px;line-height:1;cursor:pointer;",
      "padding:2px 6px;border-radius:8px;color:#c3ccd8;user-select:none;transition:transform .12s ease}",
      ".ce-star:hover{transform:scale(1.18)}",
      ".ce-star.on{color:#ffb347}",
      "body.dark .ce-star{color:#7c8798}"
    ].join(" ");
    var st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);
  }

  /* ───────── 启动 ───────── */
  function boot() {
    try { injectStyle(); } catch (e) { }
    try { ensureThemeBtn(); } catch (e) { }
    try { injectToolbar(); } catch (e) { }
    try { decorateAll(); } catch (e) { }

    // 列表是分页/异步渲染的，用 MutationObserver 保证新卡片也被装饰
    try {
      var targets = document.querySelectorAll(".list");
      for (var i = 0; i < targets.length; i++) {
        new MutationObserver(function () {
          decorateAll();
          if (favOnly) applyFavFilter();
        }).observe(targets[i], { childList: true, subtree: true });
      }
    } catch (e) { }

    // tab 切换后工具栏会重建，补一次
    try {
      new MutationObserver(function () {
        injectToolbar();
        decorateAll();
      }).observe(document.body, { childList: true, subtree: false });
    } catch (e) { }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
