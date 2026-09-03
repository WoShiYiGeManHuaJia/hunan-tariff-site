/* 中国移动资费监控面板 - 前端逻辑 */
"use strict";
const DATA = "./data/";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
));
const cache = {};

function loadJson(file) {
  if (cache[file]) return cache[file];
  return fetch(DATA + file)
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { cache[file] = j; return j; });
}

/* ---------- Tab 切换 ---------- */
const TAB_SHOWN = {};
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    tab.classList.add("active");
    const v = tab.dataset.view;
    $("view-" + v).classList.add("active");
    if (TAB_SHOWN[v]) return;
    TAB_SHOWN[v] = true;
    if (v === "overview") renderOverview();
    else if (v === "quanguo") renderList("quanguo");
    else if (v === "hunan") renderList("hunan");
    else if (v === "history") renderHistory();
  });
});

/* ---------- 数据总览 ---------- */
function renderOverview() {
  loadJson("latest.json").then((d) => {
    $("stTotal").textContent = d.quanguo_total != null ? fmt(d.quanguo_total) : "-";
    $("stHunan").textContent = d.hunan_total != null ? fmt(d.hunan_total) : "-";
    const dist = d.dist || {};
    const gr = dist["政企资费"] || {};
    $("stQuanguo").textContent = fmt(totalOf(dist["个人资费"]));
    $("stGq").textContent = fmt(totalOf(gr));
    $("updateTime").textContent = "更新于 " + (d.updated || "未知");
    document.title = "中国移动资费监控 · 更新于 " + (d.updated || "");
    renderBars(dist);
    renderHnDuo(d.hn_dist || {});
  }).catch((e) => {
    $("stTotal").textContent = "加载失败";
    $("updateTime").textContent = "加载失败";
    $("distBars").innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
}
function totalOf(o) { return (o && typeof o === "object") ? Object.values(o).reduce((a, b) => a + b, 0) : 0; }
function fmt(n) { return (n === undefined || n === null) ? "-" : n.toLocaleString("zh-CN"); }

function renderBars(dist) {
  const box = $("distBars");
  const labels = ["个人资费·套餐", "个人资费·加装包", "个人资费·营销活动", "政企资费·套餐", "政企资费·加装包", "政企资费·营销活动"];
  const rows = [];
  let max = 1;
  labels.forEach((lab) => {
    const [own, type] = lab.split("·");
    const n = ((dist[own] || {})[type]) || 0;
    rows.push({ lab, n }); if (n > max) max = n;
  });
  if (!rows.some((r) => r.n > 0)) {
    box.innerHTML = '<div class="empty">暂无分类统计</div>';
    return;
  }
  box.innerHTML = rows.map((r, i) => (
    '<div class="bar-row"><span>' + r.lab + '</span>' +
    '<div class="bar-track"><div class="bar-fill' + (i > 2 ? " alt" : "") + '" style="width:' + Math.max((r.n / max) * 100, 2) + '%"></div></div>' +
    '<span class="bar-num">' + fmt(r.n) + "</span></div>"
  )).join("");
}

function renderHnDuo(hn) {
  const order = ["套餐", "加装包", "营销活动"];
  const box = $("hnMini");
  const rows = order.map((t) => ({ t, n: hn[t] || 0 }));
  if (!rows.some((r) => r.n > 0)) { box.innerHTML = '<div class="empty">暂无数据</div>'; return; }
  box.innerHTML = rows.map((r) => (
    '<div class="mini-card"><div class="mn">' + fmt(r.n) + "</div><div class=\"ml\">湖南·" + r.t + "</div></div>"
  )).join("");
}

/* ---------- 列表（全国 / 湖南） ---------- */
const PAGE_SIZE = 20;
const listState = {
  quanguo: { items: null, page: 1, q: "", own: "", type: "" },
  hunan:   { items: null, page: 1, q: "", own: "", type: "" },
};

function renderList(section) {
  const st = listState[section];
  const listEl = $(section === "quanguo" ? "qList" : "hList");
  const pagerEl = $(section === "quanguo" ? "qPager" : "hPager");
  const cntEl = $(section === "quanguo" ? "qCount" : "hCount");
  const file = section === "quanguo" ? "quanguo.json" : "hunan.json";
  const qEl = $(section === "quanguo" ? "qSearch" : "hSearch");
  if (!st.items) {
    listEl.innerHTML = '<div class="loading">加载' + (section === "quanguo" ? "全国" : "湖南") + "资费数据（约" + (section === "quanguo" ? 2 : 2.2) + "MB，请稍候）…</div>";
  }
  loadJson(file).then((d) => {
    st.items = d.items || [];
    $("updateTime").textContent = "更新于 " + (d.timestamp || "未知");
    drawList(section);
  }).catch((e) => {
    listEl.innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
  // 绑定筛选控件（只绑一次）
  if (!qEl.dataset.bound) {
    qEl.dataset.bound = "1";
    qEl.addEventListener("input", () => { st.q = qEl.value.trim().toLowerCase(); st.page = 1; drawList(section); });
    const ownEl = $(section === "quanguo" ? "qOwn" : "hOwn");
    const typeEl = $(section === "quanguo" ? "qType" : "hType");
    if (ownEl) ownEl.addEventListener("change", () => { st.own = ownEl.value; st.page = 1; drawList(section); });
    if (typeEl) typeEl.addEventListener("change", () => { st.type = typeEl.value; st.page = 1; drawList(section); });
    $(section === "quanguo" ? "qReload" : "hReload").addEventListener("click", () => { st.items = null; renderList(section); });
  }
}

function filterItems(st) {
  const src = st.items || [];
  const out = [];
  for (const it of src) {
    if (st.own && (it.fields && it.fields["归属"]) !== st.own) continue;
    if (st.type && (it.fields && it.fields["资费类型"]) !== st.type) continue;
    if (st.q) {
      const hay = (it.name + " " + ((it.fields && it.fields["资费标准"]) || "") + " " +
        JSON.stringify(it.fields || {})).toLowerCase();
      if (!hay.includes(st.q)) continue;
    }
    out.push(it);
  }
  return out;
}

function drawList(section) {
  const st = listState[section];
  const listEl = $(section === "quanguo" ? "qList" : "hList");
  const pagerEl = $(section === "quanguo" ? "qPager" : "hPager");
  const cntEl = $(section === "quanguo" ? "qCount" : "hCount");
  const filtered = filterItems(st);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  if (st.page > totalPages) st.page = totalPages;
  const start = (st.page - 1) * PAGE_SIZE;
  const pageItems = filtered.slice(start, start + PAGE_SIZE);
  cntEl.textContent = "共 " + fmt(filtered.length) + " 条";
  if (!pageItems.length) { listEl.innerHTML = '<div class="empty">没有匹配的资费条目</div>'; }
  else {
    listEl.innerHTML = pageItems.map((it, i) => itemHtml(it, start + i)).join("");
    listEl.querySelectorAll(".item").forEach((el) => {
      el.addEventListener("click", () => {
        const d = el.querySelector(".detail");
        if (d) d.classList.toggle("open");
      });
    });
  }
  // 分页
  pagerEl.innerHTML =
    '<button ' + (st.page <= 1 ? "disabled" : "") + ' data-p="-1">上一页</button>' +
    '<span class="page-info">第 ' + st.page + " / " + totalPages + " 页</span>" +
    '<button ' + (st.page >= totalPages ? "disabled" : "") + ' data-p="1">下一页</button>';
  pagerEl.querySelectorAll("button[data-p]").forEach((b) => {
    b.addEventListener("click", () => { st.page += Number(b.dataset.p); drawList(section); window.scrollTo({ top: 0, behavior: "smooth" }); });
  });
}

function itemHtml(it, idx) {
  const f = it.fields || {};
  const own = f["归属"] || "";
  const type = f["资费类型"] || "";
  const price = f["资费标准"] || "";
  const scope = f["适用范围"] ? f["适用范围"].replace(/^限/, "限 ") : "";
  const facts = [];
  if (scope) facts.push("<span>适用：" + esc(scope) + "</span>");
  if (f["国内通话"]) facts.push("<span>通话 <b>" + esc(f["国内通话"]) + "</b></span>");
  if (f["国内通用流量"]) facts.push("<span>流量 <b>" + esc(f["国内通用流量"]) + "</b></span>");
  if (f["宽带"] && f["宽带"] !== "無" && f["宽带"] !== "无") facts.push("<span>宽带 <b>" + esc(f["宽带"]) + "</b></span>");
  const keys = Object.keys(f);
  const mainKeys = ["资费标准", "方案编号", "资费类型", "归属", "适用范围", "适用地区", "上线日期", "下线日期", "有效期限"];
  const detailRows = mainKeys.filter((k) => f[k]).map((k) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(f[k]) + "</td></tr>"
  ).join("");
  const otherKeys = keys.filter((k) => !mainKeys.includes(k) && f[k]);
  const otherRows = otherKeys.map((k) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(f[k]) + "</td></tr>"
  ).join("");
  return (
    '<div class="item">' +
      '<div class="item-head">' +
        '<span class="item-name">' + esc(it.name) + "</span>" +
        (own ? '<span class="tag ' + (own.indexOf("政企") >= 0 ? "own-gq" : "") + '">' + esc(own) + "</span>" : "") +
        (type ? '<span class="tag ' + (type === "加装包" ? "type-jz" : type === "营销活动" ? "type-yx" : "") + '">' + esc(type) + "</span>" : "") +
        (price ? '<span class="tag">' + esc(price) + "</span>" : "") +
      "</div>" +
      (facts.length ? '<div class="item-facts">' + facts.join("") + "</div>" : "") +
      '<div class="detail"><table>' + detailRows + otherRows + '</table></div>' +
    "</div>"
  );
}

/* ---------- 变化历史 ---------- */
function renderHistory() {
  loadJson("history.json").then((list) => {
    const box = $("historyBox");
    if (!Array.isArray(list) || !list.length) {
      box.innerHTML = '<div class="empty">暂无资费变化记录（首次基线已建立，后续检测到变更会自动记录）</div>';
      return;
    }
    box.innerHTML = '<div class="tl">' + list.map((r) => {
      const parts = [];
      ["quanguo", "hunan"].forEach((sec) => {
        const d = r[sec];
        if (!d) return;
        const head = sec === "quanguo" ? "全国" : "湖南";
        const chips = [];
        if (d.added) chips.push('<span class="chip add">新增 ' + d.added + "</span>");
        if (d.removed) chips.push('<span class="chip del">下架 " + d.removed + "</span>");
        if (d.modified) chips.push('<span class="chip mod">修改 ' + d.modified + "</span>");
        if (chips.length) parts.push("<div><b>" + head + "</b>：" + chips.join("") + "</div>");
      });
      return (
        '<div class="tl-item"><div class="tl-time">' + esc(r.ts || "") + "</div>" +
        '<div class="tl-chips">' + (parts.join("") || '<span class="chip">无变化</span>') + "</div></div>"
      );
    }).join("") + "</div>";
  }).catch((e) => {
    $("historyBox").innerHTML = '<div class="empty">历史数据加载失败：' + esc(e.message) + "</div>";
  });
}

/* 启动：默认总览 */
renderOverview();
