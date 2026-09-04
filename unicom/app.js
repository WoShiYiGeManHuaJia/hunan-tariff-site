/* 中国联通资费专区 - 前端 */
"use strict";
const DATA = "./data/";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PROV_KEY = "unicom_selected_prov";
const SCOPES = ["hunan", "guangdong"]; // 有数据的省份 scope；quanguo 为全国池
const NAMES = { quanguo: "全网(全国)", hunan: "湖南", guangdong: "广东" };
let DATA_CACHE = {};          // scope -> {items}
let CUR = "hunan";            // 当前省份
const FIRST_ALL = "全部";
let FIRST_LIST = [FIRST_ALL]; // 一级分类
let SECOND_LIST = [];         // 当前二级分类（联动）
const PAGE_SIZE = 20;
let st = { items: [], q: "", first: FIRST_ALL, second: "全部", page: 1 };

/* ---------- 工具 ---------- */
function fmt(n) { return (n === undefined || n === null) ? "-" : n.toLocaleString("zh-CN"); }
function confStat(el, cur) { el.innerHTML = (cur == null) ? "-" : fmt(cur); }

/* ---------- 数据加载 ---------- */
function loadJson(file) {
  if (DATA_CACHE[file]) return Promise.resolve(DATA_CACHE[file]);
  return fetch(DATA + file).then((r) => { if (!r.ok) throw new Error(file + " " + r.status); return r.json(); })
    .then((d) => { DATA_CACHE[file] = d; return d; });
}

function friendlyFees(item) {
  if (!item) return { fee: "-", extras: "" };
  const d = item.detail || {};
  const raw = item.fee || d.feesStandard;
  let fee = (raw === "" || raw == null) ? "-" : ((raw === "0" || raw === "0.") ? "免费" : raw);
  const parts = [];
  if (d.minute && d.minute !== "0") parts.push("语音 " + d.minute + "分钟");
  if (d.commonData && d.commonData !== "0") parts.push("流量 " + d.commonData + (d.dataUnit || "GB"));
  if (d.broadBand && d.broadBand !== "无") parts.push("宽带 " + d.broadBand);
  return { fee, extras: parts.join(" · ") };
}

/* ---------- 初始化 ---------- */
function init() {
  const list = document.querySelectorAll(".tab");
  list.forEach((t) => t.addEventListener("click", () => goTab(t.dataset.view)));
  const onHash = () => goTab((location.hash || "#overview").slice(1) === "list" ? "list" : "overview");
  window.addEventListener("hashchange", onHash);
  onHash();

  const mem = (() => { try { return localStorage.getItem(PROV_KEY) || ""; } catch (e) { return ""; } })();
  if (SCOPES.includes(mem)) CUR = mem;

  fillProvSelects();
  $("q").addEventListener("input", () => { st.q = $("q").value.trim(); st.page = 1; drawList(); });
  $("fLvl").addEventListener("change", () => { st.first = $("fLvl").value; syncSecond(); st.page = 1; drawList(); });
  $("sLvl").addEventListener("change", () => { st.second = $("sLvl").value; st.page = 1; drawList(); });

  renderOverview();
  drawList();
}

function goTab(v) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
  $("view-" + v).classList.add("active");
  if (v === "list") drawList();
}

function fillProvSelects() {
  const opts = SCOPES.map((s) => '<option value="' + s + '">' + NAMES[s] + "</option>").join("");
  const pProv = $("pProv"), oProv = $("oProv");
  if (pProv) {
    pProv.innerHTML = opts;
    pProv.value = CUR;
    pProv.addEventListener("change", () => { setProv(pProv.value); drawList(); });
  }
  if (oProv) {
    oProv.innerHTML = opts;
    oProv.value = CUR;
    oProv.addEventListener("change", () => { setProv(oProv.value); renderOverview(); });
  }
}

function setProv(v) {
  CUR = v;
  try { localStorage.setItem(PROV_KEY, v); } catch (e) {}
  if ($("pProv")) $("pProv").value = v;
  if ($("oProv")) $("oProv").value = v;
}

/* ---------- 数据总览 ---------- */
function renderOverview() {
  return Promise.all([loadJson("quanguo.json"), loadJson(CUR + ".json")]).then(([q, cur]) => {
    confStat($("stTotal"), q.items.length);
    $("stProvLabel").textContent = NAMES[CUR] + "资费总数";
    confStat($("stProv"), cur.items.length);
    const onsale = cur.items.filter((x) => x.firstLevel !== "停售套餐").length;
    $("stOnsaleLabel").textContent = NAMES[CUR] + "在售资费";
    confStat($("stOnsale"), onsale);

    // 分类分布
    const dist = {};
    cur.items.forEach((x) => { const k = x.firstLevel || "其他"; dist[k] = (dist[k] || 0) + 1; });
    $("distDesc").textContent = NAMES[CUR] + "口径 · 一级分类分布";
    renderBarsBox($("distBars"), dist);
  }).catch((e) => {
    $("stTotal").textContent = "加载失败";
    $("distBars").innerHTML = '<div class="empty">' + esc(e.message) + "</div>";
  });
}

function renderBarsBox(box, dist) {
  const rows = Object.keys(dist).map((k) => ({ lab: k, n: dist[k] }));
  rows.sort((a, b) => b.n - a.n);
  let max = 1;
  rows.forEach((r) => { if (r.n > max) max = r.n; });
  box.innerHTML = rows.length ? rows.map((r, i) => (
    '<div class="bar-row"><span>' + esc(r.lab) + "</span>" +
    '<div class="bar-track"><div class="bar-fill" style="width:' + Math.max((r.n / max) * 100, 2) + '%"></div></div>' +
    '<span class="bar-num">' + fmt(r.n) + "</span></div>"
  )).join("") : '<div class="empty">暂无数据</div>';
}

/* ---------- 列表 ---------- */
function getItems() {
  return loadJson(CUR + ".json").then((d) => {
    d.items.forEach((x) => { x._scope = CUR; });
    return d.items;
  });
}

function syncSecond() {
  const items = st._all || [];
  const flat = st.first === FIRST_ALL ? items : items.filter((x) => (x.firstLevel || "其他") === st.first);
  const secs = Array.from(new Set(flat.map((x) => x.secondLevel || "其他"))).sort();
  SECOND_LIST = secs;
  const sl = $("sLvl");
  sl.innerHTML = '<option value="全部">二级分类：全部</option>' + secs.map((s2) => '<option value="' + esc(s2) + '">' + esc(s2) + "</option>").join("");
  sl.value = st.second;
}

function drawList() {
  $("listHead").textContent = (NAMES[CUR]) + " · 资费列表";
  getItems().then((items) => {
    st._all = items;
    // 一级分类联动
    const fs = Array.from(new Set(items.map((x) => x.firstLevel || "其他"))).sort();
    if (!FIRST_LIST.length || JSON.stringify(FIRST_LIST.slice(1)) !== JSON.stringify(fs)) {
      const fEl = $("fLvl");
      fEl.innerHTML = '<option value="' + FIRST_ALL + '">一级分类：全部</option>' + fs.map((f) => '<option value="' + esc(f) + '">' + esc(f) + "</option>").join("");
      if (!fs.includes(st.first)) st.first = FIRST_ALL;
      fEl.value = st.first;
      FIRST_LIST = [FIRST_ALL].concat(fs);
    }
    syncSecond();

    // 过滤
    let arr = items.filter((x) => {
      if (st.first !== FIRST_ALL && (x.firstLevel || "其他") !== st.first) return false;
      if (st.second !== "全部" && (x.secondLevel || "其他") !== st.second) return false;
      if (st.q && !(-1 < (x.title || "").indexOf(st.q))) return false;
      return true;
    });
    // 排序：在售在前，fee 数值升序
    arr = arr.slice().sort((a, b) => {
      const aStop = a.firstLevel === "停售套餐" ? 1 : 0, bStop = b.firstLevel === "停售套餐" ? 1 : 0;
      if (aStop !== bStop) return aStop - bStop;
      const af = parseFloat(a.fee), bf = parseFloat(b.fee);
      if (isNaN(af) && isNaN(bf)) return 0;
      if (isNaN(af)) return 1;
      if (isNaN(bf)) return -1;
      return af - bf;
    });

    const total = arr.length;
    const pages = Math.ceil(total / PAGE_SIZE) || 1;
    if (st.page > pages) st.page = pages;
    const start = (st.page - 1) * PAGE_SIZE;
    st._filtered = arr;
    renderList(arr.slice(start, start + PAGE_SIZE), total, pages);
  }).catch((e) => {
    $("list").innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
}

function renderList(pageItems, total, pages) {
  const box = $("list");
  box.innerHTML = pageItems.length ? pageItems.map((it, i) => {
    const f = friendlyFees(it);
    const stop = it.firstLevel === "停售套餐" ? ' <span class="tag stop">停售</span>' : "";
    return '<div class="row" data-i="' + ((st.page - 1) * PAGE_SIZE + i) + '">' +
      '<div class="row-title">' + esc(it.title) + stop + "</div>" +
      '<div class="row-meta">' + esc(it.firstLevel || "") + " / " + esc(it.secondLevel || "") + "</div>" +
      '<div class="row-fee">' + esc(f.fee) + "</div>" +
      "</div>";
  }).join("") : '<div class="empty">没有匹配的资费</div>';

  $("pager").innerHTML = pages > 1
    ? '<button ' + (st.page <= 1 ? "disabled" : "") + ' data-p="-1">上一页</button>' +
      '<span class="pg-info">' + st.page + " / " + pages + "（共 " + fmt(total) + " 条）</span>" +
      '<button ' + (st.page >= pages ? "disabled" : "") + ' data-p="1">下一页</button>'
    : '<span class="pg-info">共 ' + fmt(total) + " 条</span>";

  box.querySelectorAll(".row").forEach((row) => {
    row.addEventListener("click", () => {
      const idx = parseInt(row.dataset.i, 10);
      showDetail(st._filtered[idx]);
    });
  });
  $("pager").querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => { st.page += parseInt(b.dataset.p, 10); drawList(); });
  });
}

/* ---------- 明细 ---------- */
function showDetail(item) {
  const d = item.detail || {};
  const f = friendlyFees(item);
  const rows = [
    ["资费类型", (d.codeType || item.firstLevel || "") + (item.firstLevel === "停售套餐" ? "（停售）" : "")],
    ["月费标准", (d.feesStandard || item.fee || "-") + (d.feeUnit ? " " + d.feeUnit : "")],
    ["语音", (d.minute && d.minute !== "0") ? d.minute + " 分钟" : "无"],
    ["流量", (d.commonData && d.commonData !== "0") ? d.commonData + " " + (d.dataUnit || "GB") : "无"],
    ["短信", (d.sms && d.sms !== "0") ? d.sms + " 条" : "无"],
    ["定向流量", (d.orientTraffic && d.orientTraffic !== "0") ? d.orientTraffic + (d.orientTrafficUnit || "") : "无"],
    ["IPTV", d.iptv || "无"],
    ["宽带", d.broadBand && d.broadBand !== "无" ? d.broadBand : "无"],
    ["套餐内容", d.serviceContent || "-"],
    ["适用对象", d.useScope || "-"],
    ["有效期", d.validPeriod || "-"],
    ["其他收费", d.extraFees && d.extraFees !== "无" ? d.extraFees : "无"],
    ["办理渠道", d.saleChnl || "-"],
    ["停售状态", item.firstLevel === "停售套餐" ? "已停售" : "在售"],
  ];
  const html = '<div class="detail-name">' + esc(item.title) + "</div>" +
    '<div class="detail-fee">' + esc(f.fee) + '</div>' +
    rows.filter(([, v]) => v && v !== "-" && v !== "").map(([k, v]) => (
      '<div class="drow"><span class="dkey">' + k + "</span><span class='dval'>" + esc(v) + "</span></div>"
    )).join("");
  $("modalBody").innerHTML = html;
  $("overlay").hidden = false;
}
$("closeModal") && document.getElementById("closeModal").addEventListener("click", closeModal);
$("overlay") && document.getElementById("overlay").addEventListener("click", (e) => { if (e.target.id === "overlay") closeModal(); });
function closeModal() { $("overlay").hidden = true; }

init();
