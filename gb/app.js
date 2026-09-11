/* 中国广电资费专区 - 前端逻辑(vgb20260911c: 省份选择弹窗美化+顶部固定搜索; 数据来源广电官网公示) */
"use strict";
const DATA = "./data/";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
));
const cache = {};

const FETCH_TIMEOUT = 20000;
function fetchTimeout(url, init) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT);
  return fetch(url, Object.assign({}, init || {}, { signal: ctrl.signal }))
    .catch((e) => { if (e && e.name === "AbortError") throw new Error("加载超时，请检查网络后重试"); throw e; })
    .finally(() => clearTimeout(t));
}
function loadJson(file) {
  if (cache[file]) return Promise.resolve(cache[file]);
  return fetchTimeout(DATA + file)
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { cache[file] = j; return j; });
}

/* ---------- 板块索引 ---------- */
let SECTIONS = [];
let DEF_SECTION = "hunan";
const PROV_KEY = "gb_selected_prov";
function provList() { return SECTIONS.filter((s) => s.section !== "quanguo"); }
function secName(sec) { const s = SECTIONS.find((x) => x.section === sec); return s ? s.name : sec; }

let sectorsLoaded = null;
function ensureSections() {
  if (sectorsLoaded) return sectorsLoaded;
  sectorsLoaded = loadJson("latest.json").then((d) => {
    SECTIONS = d.sections || [];
    DEF_SECTION = d.default || DEF_SECTION;
    fillProvSelects();
    return d;
  }).catch(() => {});
  return sectorsLoaded;
}

/* ---------- 省份选择弹窗（按钮触发 + 顶部固定搜索栏） ---------- */
let PROV_PICKER = null; // 当前弹窗关联的 select id
function syncProvTxt(selId) {
  const txt = $(selId + "Txt");
  if (!txt) return;
  const sel = $(selId);
  const v = (sel && sel.value) || "";
  txt.textContent = v === "" ? "全部省份" : (secName(v) || v);
}
function openProvPicker(selId) {
  PROV_PICKER = selId;
  const s = $("provSearch"); if (s) s.value = "";
  renderProvGrid();
  const b = $(selId + "Btn"); if (b) b.classList.add("open");
  $("provMask").classList.add("show");
}
function closeProvPicker() {
  $("provMask").classList.remove("show");
  if (PROV_PICKER) { const b = $(PROV_PICKER + "Btn"); if (b) b.classList.remove("open"); }
  PROV_PICKER = null;
}
function renderProvGrid() {
  const grid = $("provGrid"); if (!grid) return;
  const items = provList().map((s) => ({ section: s.section, name: s.name }));
  if (PROV_PICKER === "hProvFilter") items.unshift({ section: "", name: "全部省份" });
  const cur = (PROV_PICKER && $(PROV_PICKER)) ? ($(PROV_PICKER).value || "") : "";
  const s = $("provSearch");
  const k = (s ? s.value : "").trim().toLowerCase();
  const list = k ? items.filter((it) => it.name.toLowerCase().indexOf(k) >= 0) : items;
  if (!list.length) { grid.innerHTML = '<div class="prov-empty">未找到匹配省份</div>'; return; }
  grid.innerHTML = list.map((it) => {
    const on = it.section === cur;
    return '<button type="button" class="prov-cell' + (on ? " on" : "") + '" data-sec="' + esc(it.section) + '">' +
      "<span>" + esc(it.name) + '</span><span class="tick">✓</span></button>';
  }).join("");
  grid.querySelectorAll(".prov-cell").forEach((cell) => {
    cell.addEventListener("click", () => pickProv(cell.dataset.sec));
  });
}
function pickProv(sec) {
  if (!PROV_PICKER) return;
  const sel = $(PROV_PICKER); if (!sel) return;
  sel.value = sec;
  sel.dispatchEvent(new Event("change"));
  closeProvPicker();
}
function initProvPicker() {
  const c = $("provClose"); if (c) c.addEventListener("click", closeProvPicker);
  const m = $("provMask"); if (m) m.addEventListener("click", (e) => { if (e.target === m) closeProvPicker(); });
  const s = $("provSearch"); if (s) s.addEventListener("input", renderProvGrid);
}

function fillProvSelects() {
  const provEl = $("pProv");
  const oProv = $("oProv");
  const opts = provList().map((s) => '<option value="' + esc(s.section) + '">' + esc(s.name) + "</option>").join("");
  if (provEl && provEl.options.length === 0) {
    provEl.innerHTML = opts;
    let mem = "";
    try { mem = localStorage.getItem(PROV_KEY) || ""; } catch (e) {}
    provEl.value = provList().some((s) => s.section === mem) ? mem : DEF_SECTION;
    provEl.addEventListener("change", () => {
      const v = provEl.value;
      try { localStorage.setItem(PROV_KEY, v); } catch (e) {}
      if (oProv && oProv.options.length) oProv.value = v;
      if (oProv) syncProvTxt("oProv");
      syncProvTxt("pProv");
      listState.prov = null;
      renderList("prov");
    });
    syncProvTxt("pProv");
    const pBtn = $("pProvBtn"); if (pBtn) pBtn.addEventListener("click", () => openProvPicker("pProv"));
  }
  if (oProv && oProv.options.length === 0) {
    oProv.innerHTML = opts;
    let mem = "";
    try { mem = localStorage.getItem(PROV_KEY) || ""; } catch (e) {}
    oProv.value = provList().some((s) => s.section === mem) ? mem : DEF_SECTION;
    oProv.addEventListener("change", () => {
      const v = oProv.value;
      try { localStorage.setItem(PROV_KEY, v); } catch (e) {}
      if (provEl && provEl.options.length) provEl.value = v;
      if (provEl) syncProvTxt("pProv");
      syncProvTxt("oProv");
      renderProvPanel();
    });
    syncProvTxt("oProv");
    const oBtn = $("oProvBtn"); if (oBtn) oBtn.addEventListener("click", () => openProvPicker("oProv"));
  }
  const hfEl = $("hProvFilter");
  if (hfEl && hfEl.options.length === 0) {
    let hopts = '<option value="">全部省份</option>';
    hopts += provList().map((s) => '<option value="' + esc(s.section) + '">' + esc(s.name) + "</option>").join("");
    hfEl.innerHTML = hopts;
    hfEl.addEventListener("change", () => { syncProvTxt("hProvFilter"); renderHistory(); });
    syncProvTxt("hProvFilter");
    const hBtn = $("hProvFilterBtn"); if (hBtn) hBtn.addEventListener("click", () => openProvPicker("hProvFilter"));
  }
}

/* ---------- Tab 切换（支持 hash 直达） ---------- */
const TAB_SHOWN = {};
function goTab(v) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  document.querySelectorAll(".view").forEach((x) => x.classList.remove("active"));
  $("view-" + v).classList.add("active");
  if (TAB_SHOWN[v]) return;
  TAB_SHOWN[v] = true;
  if (v === "overview") renderOverview();
  else if (v === "quanguo") renderList("quanguo");
  else if (v === "prov") { ensureSections(); renderList("prov"); }
  else if (v === "history") { ensureSections(); renderHistory(); }
}
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    goTab(tab.dataset.view);
    try { history.replaceState(null, "", "#" + tab.dataset.view); } catch (e) {}
  });
});

/* ---------- 数据总览 ---------- */
function fmt(n) { return (n === undefined || n === null) ? "-" : n.toLocaleString("zh-CN"); }
function confStat(el, cur) { el.innerHTML = (cur == null) ? "-" : fmt(cur); }

let LATEST = null;
function renderOverview() {
  loadJson("latest.json").then((d) => {
    LATEST = d;
    SECTIONS = d.sections || [];
    DEF_SECTION = d.default || DEF_SECTION;
    fillProvSelects();
    $("stTotal").textContent = (d.quanguo_total == null) ? "-" : fmt(d.quanguo_total);
    $("stAllProv").textContent = (d.prov_total == null) ? "-" : fmt(d.prov_total);
    $("updateTime").textContent = "更新于 " + (d.updated || "未知");
    document.title = "中国广电资费专区 · 更新于 " + (d.updated || "");
    renderProvPanel();
  }).catch((e) => {
    $("stTotal").textContent = "加载失败";
    $("distBars").innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
}

/* 总览页「本省总数/在售」卡 + 省份面板：随 oProv 联动 */
function renderProvPanel() {
  const provEl = $("oProv");
  if (!provEl) return;
  if (!provEl.options.length) fillProvSelects();
  const sec = provEl.value || DEF_SECTION;
  const st = (LATEST && LATEST.prov_stats) ? (LATEST.prov_stats[sec] || null) : null;
  const name = secName(sec);
  $("opLabel").textContent = name + "资费总数";
  $("stQuanguoLabel").textContent = name + "资费总数";
  $("stGqLabel").textContent = name + "在售资费";
  $("distDesc").textContent = name + "口径 · 五大类分布";
  if (!st) {
    confStat($("opTotal"), null); confStat($("stQuanguo"), null); confStat($("stGq"), null);
    $("distBars").innerHTML = '<div class="empty">暂无该省统计</div>';
    return;
  }
  confStat($("opTotal"), st.total);
  confStat($("stQuanguo"), st.total);
  confStat($("stGq"), st.onsale);
  renderBarsBox($("distBars"), st.dist || {});
}

const LT_LABELS = ["套餐", "加装包", "营销活动", "特殊群体套餐", "政企"];
function renderBarsBox(box, dist) {
  if (!box) return;
  const rows = [];
  let max = 1;
  LT_LABELS.forEach((lab) => {
    const n = dist[lab] || 0;
    rows.push({ lab, n }); if (n > max) max = n;
  });
  if (!rows.some((r) => r.n > 0)) { box.innerHTML = '<div class="empty">暂无分类统计</div>'; return; }
  box.innerHTML = rows.map((r, i) => (
    '<div class="bar-row"><span>' + r.lab + '</span>' +
    '<div class="bar-track"><div class="bar-fill' + (r.lab === "停售套餐" ? " alt" : "") + '" style="width:' + Math.max((r.n / max) * 100, 2) + '%"></div></div>' +
    '<span class="bar-num">' + fmt(r.n) + "</span></div>"
  )).join("");
}

/* ---------- 列表（全国 / 省份） ---------- */
const PAGE_SIZE = 20;
const listState = {};
function liveSec() {
  const el = document.getElementById("pProv");
  return (el && el.value) || DEF_SECTION;
}
function getSt(section) {
  if (!listState[section]) listState[section] = { items: null, page: 1, q: "", scope: "all", type: "", sub: "" };
  return listState[section];
}
function domMap(section) {
  if (section === "quanguo") {
    return { list: "qList", pager: "qPager", cnt: "qCount", search: "qSearch", scope: "qScope", type: "qType", sub: "qSub", reload: "qReload" };
  }
  return { list: "pList", pager: "pPager", cnt: "pCount", search: "pSearch", scope: "pScope", type: "pType", sub: "pSub", reload: "pReload" };
}

const TYPE_FIRST = { "套餐": 1, "加装包": 1, "营销活动": 1, "标准资费": 1, "港澳台/国际资费": 1, "停售套餐": 1 };
function firstLevelOf(it) { return it.firstLevel || "其他"; }
function secondLevelOf(it) { return it.secondLevel || "其他"; }

function renderList(section) {
  const rawKey = section; // 原始视图键：quanguo / prov
  if (section === "prov") { section = ((document.getElementById("pProv") || {}).value || "hunan"); }
  if (section !== "quanguo") { ensureSections(); }
  const st = getSt(section);
  const idm = domMap(section);
  const listEl = $(idm.list);
  const file = section === "quanguo" ? "quanguo.json" : section + ".json";
  const label = section === "quanguo" ? "全国" : (secName(section) || section);
  const qEl = $(idm.search);
  if (!st.items) { listEl.innerHTML = '<div class="loading">加载' + esc(label) + "资费数据（请稍候）…</div>"; }
  loadJson(file).then((d) => {
    st.items = d.items || [];
    $("updateTime").textContent = "更新于 " + (d.timestamp || "未知");
    if (section !== "quanguo") { $("pProv").value = (provList().some((s) => s.section === section) ? section : $("pProv").value); syncProvTxt("pProv"); }
    drawList(section);
  }).catch((e) => { listEl.innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>"; });

  if (!qEl.dataset.bound) {
    const secOf = () => (rawKey === "quanguo" ? "quanguo" : liveSec());
    const stOf = () => getSt(secOf());
    qEl.dataset.bound = "1";
    qEl.addEventListener("input", () => { const st = stOf(); st.q = qEl.value.trim().toLowerCase(); st.page = 1; drawList(secOf()); });
    const scopeEl = idm.scope ? $(idm.scope) : null;
    if (scopeEl) scopeEl.addEventListener("change", () => { const st = stOf(); st.scope = scopeEl.value; st.page = 1; drawList(secOf()); });
    const typeEl = $(idm.type);
    const subEl = $(idm.sub);
    if (typeEl) typeEl.addEventListener("change", () => { const st = stOf(); st.type = typeEl.value; st.page = 1; drawList(secOf()); });
    if (subEl) subEl.addEventListener("change", () => { const st = stOf(); st.sub = subEl.value; st.page = 1; drawList(secOf()); });
    $(idm.reload).addEventListener("click", () => { const st = stOf(); st.items = null; renderList(secOf()); });
    setupSortBar(rawKey);
  }
}

/* ---------- 资费排序（最新上架 / 价格 / 方向） ---------- */
function timeOf(it) {
  const f = it.fields || it.detail || {};
  const s = f["上线日期"] || "";
  if (s) {
    const m = s.match(/20\d{2}\D+(\d{1,2})\D+(\d{1,2})/);
    if (m) { const y = s.match(/20\d{2}/)[0]; return new Date(+y, (+m[1]) - 1, +m[2]).getTime(); }
  }
  const rp = ((it.detail || {}).reportNo || "").match(/^(\d{2})/);
  if (rp) return new Date(2000 + +rp[1], 0, 1).getTime();
  const vp = ((it.detail || {}).validPeriod || "") + " " + ((it.detail || {}).serviceContent || "");
  const vm = vp.match(/20\d{2}/);
  return vm ? new Date(+vm[0], 0, 1).getTime() : 0;
}
function priceOf(it) {
  if (it.fields) {
    const raw = it.fields["资费标准"] || (isFinite(parseFloat(it.fee)) ? it.fee : "");
    const m = String(raw).match(/\d+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : 0;
  }
  const n = parseFloat(it.fee);
  if (isFinite(n)) return n;
  const d = it.detail || {};
  const dm = String(d.feesStandard || "").match(/\d+(?:\.\d+)?/);
  return dm ? parseFloat(dm[0]) : 0;
}
/* ---- 零元业务：筛选当前省份/全国中费用为 0 的资费；免费/0元每月在前、0元每次在后 ---- */
function isZeroFee(it) {
  if (it.fields) {
    const raw = String(it.fields["资费标准"] || "");
    if (/免费/.test(raw)) return true;
    const m = raw.match(/\d+(?:\.\d+)?/);
    return !!m && Math.abs(parseFloat(m[0])) < 1e-9;
  }
  const fv = String(it.fee == null ? "" : it.fee).trim();
  const dv = String(((it.detail || {}).feesStandard == null ? "" : it.detail.feesStandard)).trim();
  const zero = (n) => { if (n === "") return false; const v = parseFloat(n); return !isNaN(v) && Math.abs(v) < 1e-9; };
  return zero(fv) || zero(dv);
}
function zeroRank(it) {
  if (it.fields) {
    const raw = String(it.fields["资费标准"] || "");
    if (/次/.test(raw)) return 2;                 // 0元/次 → 后排
    if (/月/.test(raw) || /免费/.test(raw)) return 0; // 0元/月、免费 → 前排
    return 1;
  }
  const u = String(((it.detail || {}).feeUnit) || "");
  if (/次/.test(u)) return 2;                     // 每次 → 后排
  if (/月|天/.test(u)) return 0;                  // 元/月、元/30天 等 → 前排
  const fv = String(it.fee == null ? "" : it.fee);
  if (/免费/.test(fv)) return 0;
  return 1;
}
function sortFiltered(arr, st) {
  const dir = (st.order == null ? -1 : st.order) < 0 ? -1 : 1; // 默认降序
  arr.sort(function (a, b) {
    if (!st.sort) return 0;
    const av = st.sort === "price" ? priceOf(a) : timeOf(a);
    const bv = st.sort === "price" ? priceOf(b) : timeOf(b);
    if (av === 0 && bv !== 0) return 1;  // 无法解析的排后
    if (bv === 0 && av !== 0) return -1;
    if (av === bv) return 0;
    return (av > bv ? 1 : -1) * dir;
  });
}
function setupSortBar(rawKey) {
  if (rawKey !== "quanguo" && rawKey !== "prov") return;
  const bar = document.getElementById((rawKey === "quanguo" ? "q" : "p") + "SortBar");
  if (!bar || bar.dataset.bound) return;
  bar.dataset.bound = "1";
  bar.querySelectorAll(".sort-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sec = rawKey === "quanguo" ? "quanguo" : liveSec();
      const st = getSt(sec);
      const sort = btn.dataset.sort;
      if (sort === "zero") { st.zero = !st.zero; }
      else if (sort === "dir") { st.order = (st.order == null ? -1 : st.order) * -1; }
      else { st.sort = sort; st.order = sort === "price" ? 1 : -1; }
      st.page = 1;
      syncSortUI(bar, st);
      drawList(sec);
    });
  });
  syncSortUI(bar, getSt(rawKey === "quanguo" ? "quanguo" : liveSec()));
}
function syncSortUI(bar, st) {
  if (!bar) return;
  bar.querySelectorAll(".sort-btn[data-sort]").forEach((b) => {
    const s = b.dataset.sort;
    if (s !== "dir" && s !== "zero") b.classList.toggle("active", !!st.sort && st.sort === s);
  });
  const z = bar.querySelector('.sort-btn[data-sort="zero"]');
  if (z) z.classList.toggle("active", !!st.zero);
  const d = bar.querySelector('.sort-btn[data-sort="dir"]');
  if (d) d.textContent = (st.order == null ? -1 : st.order) < 0 ? "降序 ↓" : "升序 ↑";
}

function filterItems(st) {
  const src = st.items || [];
  const out = [];
  for (const it of src) {
    if (st.zero && !isZeroFee(it)) continue;
    if (st.type) {
      const sub = firstLevelOf(it);
      if (sub === "停售套餐") { if (st.type !== "停售套餐") continue; }
      else if (sub !== st.type) continue;
    }
    if (st.sub && secondLevelOf(it) !== st.sub) continue;
    if (st.q) {
      if (st.scope === "name") {
        if ((it.title || "").toLowerCase().indexOf(st.q) < 0) continue;
      } else {
        const d = it.detail || {};
        const hay = [it.title, it.fee, d.feesStandard, d.serviceContent, d.useScope, d.codeType,
          firstLevelOf(it), secondLevelOf(it)].filter((v) => v != null && v !== "").join(" ").toLowerCase();
        if (!hay.includes(st.q)) continue;
      }
    }
    out.push(it);
  }
  return out;
}

function drawList(section) {
  if (section !== "quanguo") section = liveSec();
  const st = getSt(section);
  const idm = domMap(section);
  const listEl = $(idm.list);
  const pagerEl = $(idm.pager);
  const cntEl = $(idm.cnt);
  // 二级分类联动（数据加载后同步一次可选值）
  const allSubs = Array.from(new Set((st.items || []).map((x) => secondLevelOf(x)))).sort();
  const subEl = $(idm.sub);
  if (subEl && allSubs.length && subEl.options.length <= 1) {
    subEl.innerHTML = '<option value="">全部二级分类</option>' + allSubs.map((s) => '<option>' + esc(s) + "</option>").join("");
    if (st.sub && allSubs.indexOf(st.sub) < 0) st.sub = "";
    subEl.value = st.sub;
    syncFPick(idm.sub);
  }
  const filtered = filterItems(st);
  if (st.zero) { filtered.sort((a, b) => zeroRank(a) - zeroRank(b)); }
  else if (st.sort) { sortFiltered(filtered, st); }
  else {
    filtered.sort((a, b) => {
      const aStop = firstLevelOf(a) === "停售套餐" ? 1 : 0;
      const bStop = firstLevelOf(b) === "停售套餐" ? 1 : 0;
      if (aStop !== bStop) return aStop - bStop;
      const af = parseFloat(a.fee), bf = parseFloat(b.fee);
      if (isNaN(af)) return 1; if (isNaN(bf)) return -1;
      return af - bf;
    });
  }
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
  pagerEl.innerHTML =
    '<button ' + (st.page <= 1 ? "disabled" : "") + ' data-p="-1">上一页</button>' +
    '<span class="page-info">第 ' + st.page + " / " + totalPages + " 页</span>" +
    '<button ' + (st.page >= totalPages ? "disabled" : "") + ' data-p="1">下一页</button>';
  pagerEl.querySelectorAll("button[data-p]").forEach((b) => {
    b.addEventListener("click", () => { st.page += Number(b.dataset.p); drawList(section); window.scrollTo({ top: 0, behavior: "smooth" }); });
  });
}

function friendlyFees(item) {
  if (!item) return { fee: "-", extras: "" };
  const d = item.detail || {};
  const raw = item.fee || d.feesStandard;
  let fee = (raw === "" || raw == null) ? "-" : ((raw === "0" || raw === "0.") ? "免费" : raw);
  if (d.feeUnit && fee !== "免费" && fee !== "-") fee += " " + d.feeUnit;
  const parts = [];
  if (d.minute && d.minute !== "0") parts.push("语音 " + d.minute + "分钟");
  if (d.commonData && d.commonData !== "0") parts.push("流量 " + d.commonData + (d.dataUnit || "GB"));
  if (d.broadBand && d.broadBand !== "无") parts.push("宽带 " + d.broadBand);
  return { fee, extras: parts.join(" · ") };
}

function itemHtml(it, idx) {
  const stop = firstLevelOf(it) === "停售套餐";
  const f = friendlyFees(it);
  const d = it.detail || {};
  const facts = [];
  if (d.serviceContent) facts.push("<span>内容：" + esc(String(d.serviceContent).slice(0, 40)) + "</span>");
  if (d.useScope) facts.push("<span>适用：" + esc(String(d.useScope).slice(0, 24)) + "</span>");
  if (d.minute && d.minute !== "0") facts.push("<span>语音 <b>" + esc(d.minute) + " 分钟</b></span>");
  if (d.commonData && d.commonData !== "0") facts.push("<span>流量 <b>" + esc(d.commonData + (d.dataUnit || "GB")) + "</b></span>");
  const mainKeys = ["资费类型", "月费标准", "语音", "流量", "短信", "定向流量", "宽带", "有效期", "销售渠道", "上线日期", "下线日期", "在网要求", "退订方式", "违约责任", "停售状态", "业务编码", "套餐内容", "适用对象", "其他收费"];
  const rows = detailRows(it);
  // 官方「其他说明」字段(otherNotes)固定折叠为「其他说明」，与移动站一致；其余常规字段在主表展示
  const NOTE_KEYS = ["其他说明"];
  const noteRows = rows.filter(([k, v]) => v && NOTE_KEYS.indexOf(k) >= 0);
  const notNotes = rows.filter(([k, v]) => !(v && NOTE_KEYS.indexOf(k) >= 0));
  const filteredRows = notNotes.filter(([k]) => mainKeys.indexOf(k) >= 0).map(([k, v]) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(v) + "</td></tr>").join("");
  const otherRows = notNotes.filter(([k]) => mainKeys.indexOf(k) < 0).map(([k, v]) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(v) + "</td></tr>").join("");
  const noteHtml = noteRows.map(([k, v]) =>
    '<div class="note-item"><div class="note-label">' + esc(k) + '</div>' +
    '<div class="note-text">' + esc(v) + "</div></div>"
  ).join("");
  const noteBlock = noteHtml
    ? '<div class="notes-block">' +
        '<div class="notes-toggle" role="button" tabindex="0" aria-expanded="false">其他说明' +
        '<span class="notes-arrow"></span></div>' +
        '<div class="notes-body">' + noteHtml + "</div>" +
      "</div>"
    : "";
  return (
    '<div class="item">' +
      '<div class="item-head">' +
        '<span class="item-name">' + esc(it.title) + (stop ? ' <span class="tag stop">停售</span>' : "") + "</span>" +
        '<span class="tag">' + esc(firstLevelOf(it)) + "</span>" +
        '<span class="tag type-sub">' + esc(secondLevelOf(it)) + "</span>" +
        '<span class="tag fee-tag">' + esc(f.fee) + "</span>" +
      "</div>" +
      (f.extras ? '<div class="item-facts">' + f.extras + "</div>" : "") +
      (facts.length ? '<div class="item-facts">' + facts.join("") + "</div>" : "") +
      '<div class="detail"><table>' + filteredRows + otherRows + '</table>' + noteBlock + '</div>' +
    "</div>"
  );
}

function detailRows(item) {
  const d = item.detail || {};
  const stop = firstLevelOf(item) === "停售套餐";
  const f = friendlyFees(item);
  const rows = [
    ["资费类型", (d.codeType || firstLevelOf(item)) + (stop ? "（停售）" : "")],
    ["月费标准", (d.feesStandard || item.fee || "-") + (d.feeUnit ? " " + d.feeUnit : "")],
    ["语音", (d.minute && d.minute !== "0") ? d.minute + " 分钟" : "无"],
    ["流量", (d.commonData && d.commonData !== "0") ? d.commonData + " " + (d.dataUnit || "GB") : "无"],
    ["短信", (d.sms && d.sms !== "0") ? d.sms + " 条" : "无"],
    ["定向流量", (d.orientTraffic && d.orientTraffic !== "0") ? d.orientTraffic : "无"],
    ["宽带", d.broadBand && d.broadBand !== "无" ? d.broadBand : "无"],
    ["套餐内容", d.serviceContent || "-"],
    ["适用对象", d.useScope || "-"],
    ["有效期", d.validPeriod || "-"],
    ["其他收费", d.extraFees && d.extraFees !== "无" ? d.extraFees : "无"],
    ["销售渠道", d.saleChnl || "-"],
    ["上线日期", d.onDate || "-"],
    ["下线日期", d.offDate || "-"],
    ["在网要求", d.inNetReq || "-"],
    ["退订方式", d.unsubscribe || "-"],
    ["违约责任", d.responsibility || "-"],
    ["其他说明", d.otherNotes || "-"],
    ["停售状态", stop ? "已停售" : "在售"],
    ["业务编码", d.reportNo || "-"],
  ];
  return rows.filter(([, v]) => v && v !== "-" && v !== "");
}

/* ---------- 变化历史 ---------- */
const _histCache = new Map();   // ts -> 历史记录对象，供「修改业务」明细弹窗查询
function aesc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); }

function histDetail(d, sec, ts) {
  if (!d || typeof d !== "object") return "";
  let html = "";
  [["added", "add", "新增", "added"], ["removed", "del", "下架", "removed"], ["modified", "mod", "修改", "modified"]].forEach(([key, cls, lab, kind]) => {
    const n = d[key] || 0;
    if (!n) return;
    html += '<div class="tl-sec"><span class="chip ' + cls + '">' + lab + " " + n + " 条</span>";
    const names = Array.isArray(d[key + "_names"]) ? d[key + "_names"] : null;
    if (names && names.length) {
      // 新增/下架/修改 均可点击查看详情
      html += '<ul class="tl-names">' + names.map((x) =>
        '<li class="tl-k ' + cls + '"><a class="tl-mod" href="javascript:void(0)" ' +
        'data-ts="' + aesc(ts) + '" data-sec="' + aesc(sec) + '" data-name="' + aesc(x) + '" data-kind="' + kind + '" ' +
        'title="点击查看该业务详情" ' +
        'onclick="event.stopPropagation();showPlanDetail(this.dataset.ts,this.dataset.sec,this.dataset.name,this.dataset.kind)">' +
        esc(x) + "</a>" +
        (((d[key + "_list"] && d[key + "_list"].length) || (d[key + "_details"] && d[key + "_details"][x])) ? '<span class="mod-badge">查看详情</span>' : "") +
        "</li>"
      ).join("") + "</ul>";
    } else {
      html += '<div class="tl-none">本次' + lab + " " + n + " 条，可在对应资费列表查看</div>";
    }
    html += "</div>";
  });
  return html;
}

/* 通用业务详情弹窗：历史页 新增/下架/修改 三类都可点开。
   优先读历史记录保存的详情（_list 精简详情 或 _details 字段快照），否则兜底从当前板块数据按名称查找。 */
const PLAN_LABELS = {
  title: "业务名称", fee: "月费", firstLevel: "一级分类", secondLevel: "二级分类",
  feesStandard: "资费标准", feeUnit: "计费单位", minute: "语音(分钟)", commonData: "流量",
  dataUnit: "流量单位", orientTraffic: "定向流量", validPeriod: "有效期", saleChnl: "办理渠道",
  serviceContent: "套餐内容", codeType: "资费类型", reportNo: "业务编码", extraFees: "其他收费",
  useScope: "适用对象", broadBand: "宽带", sms: "短信", onlinePeriod: "在售时间",
};
function briefTable(o) {
  if (!o || typeof o !== "object") return '<div class="tl-none">该记录未保存配置详情。</div>';
  const entries = Object.entries(o).filter(([k, v]) => v !== undefined && v !== null && String(v) !== "" && v !== "0");
  if (!entries.length) return '<div class="tl-none">该记录未保存配置详情。</div>';
  return '<table class="gen-table"><tbody>' + entries.map(([k, v]) =>
    '<tr><th>' + esc(PLAN_LABELS[k] || k) + '</th><td>' + esc(typeof v === "object" ? JSON.stringify(v) : v) + "</td></tr>"
  ).join("") + "</tbody></table>";
}
function showPlanDetail(ts, sec, name, kind) {
  const rec = _histCache.get(ts);
  const d = rec ? rec[sec] : null;
  const head = '<div class="res-row sub">变更时间：' + esc(ts) + " · " + esc(secName(sec)) + "</div>";
  if (kind === "modified") {
    const details = (d && d.modified_details && d.modified_details[name]) || null;
    if (details && details.length) {
      const rows = details.map((dt) => {
        const normV = (v) => (typeof v === "string" && /^0{2,}$/.test(v) ? "全国（不限定省份）" : v);
        return '<div class="mod-row">' +
          '<div class="mod-f">' + esc(dt.field || "") + "</div>" +
          '<div class="mod-v"><div class="mod-old" title="修改前">' + esc(normV(dt.from) || "（空）") + "</div>" +
          '<div class="mod-arrow">→</div><div class="mod-new" title="修改后">' + esc(normV(dt.to) || "（空）") + "</div></div></div>";
      }).join("");
      openModal(name, head + '<div class="res-row sub">该业务本次字段级修改（共 ' + details.length + " 项）：</div>" +
        '<div class="mod-diff">' + rows + "</div>");
      return;
    }
  }
  const nm = String(name == null ? "" : name).trim();
  let brief = null;
  const lst = (d && d[kind + "_list"]) || null;
  if (Array.isArray(lst) && lst.length) {
    brief = lst.find((x) => x && String(x.title || x.name || "").trim() === nm) || lst[0];
  }
  const snap = (d && d[kind + "_details"] && d[kind + "_details"][name]) || null;
  if (brief || snap) {
    const lab = kind === "added" ? "新增" : kind === "removed" ? "下架" : "修改";
    openModal(name, head + '<div class="res-row sub">该业务本次' + lab + '，配置如下：</div><div class="gen-brief">' +
      briefTable(snap || brief) + "</div>");
    return;
  }
  // 兜底：从当前板块数据按名称查找
  const file = sec === "quanguo" ? "quanguo.json" : sec + ".json";
  loadJson(file).then((j) => {
    const items = (j && j.items) || [];
    const it = items.find((x) => x && String(x.title || x.name || "").trim() === nm);
    if (it) {
      const fields = it.detail || it.fields || it;
      openModal(name, head + '<div class="res-row sub">当前板块中的配置：</div><div class="gen-brief">' + briefTable(fields) + "</div>");
    } else if (kind === "removed") {
      openModal(name, head + '<div class="res-row">该套餐已从板块下架，线上无剩余配置。</div>');
    } else {
      openModal(name, head + '<div class="res-row">未找到该业务配置。</div>');
    }
  }).catch((e) => {
    openModal(name, head + '<div class="res-row">加载详情失败：' + esc(e.message) + "</div>");
  });
}

/* 修改业务明细弹窗：展示该业务本次被修改的字段（旧值 → 新值） */
function showModDetail(ts, sec, name) {
  const rec = _histCache.get(ts);
  const d = rec ? rec[sec] : null;
  const details = (d && d.modified_details) ? d.modified_details[name] : null;
  const head = '<div class="res-row sub">变更时间：' + esc(ts) + " · " + esc(secName(sec)) + "</div>";
  if (!details || !details.length) {
    openModal(name, head + '<div class="res-row">该记录未保存字段级修改明细。</div>' +
      '<div class="res-row sub">可在「' + esc(secName(sec)) + '资费」列表查看该业务当前配置。</div>');
    return;
  }
  const rows = details.map((dt) => {
    const pf = esc(dt.field || "");
    const normV = (v) => (typeof v === "string" && /^0{2,}$/.test(v) ? "全国（不限定省份）" : v);
    const pv = esc(normV(dt.from) || "（空）");
    const nv = esc(normV(dt.to) || "（空）");
    return '<div class="mod-row">' +
      '<div class="mod-f">' + pf + "</div>" +
      '<div class="mod-v">' +
      '<div class="mod-old" title="修改前"><span class="mod-lab old">修改前</span>' + pv + "</div>" +
      '<div class="mod-new" title="修改后"><span class="mod-lab new">修改后</span>' + nv + "</div>" +
      "</div></div>";
  }).join("");
  openModal(name, head +
    '<div class="res-row sub">该业务本次字段级修改（共 ' + details.length + " 项）：</div>" +
    '<div class="mod-diff">' + rows + "</div>");
}

function renderHistory() {
  const filter = $("hProvFilter") ? $("hProvFilter").value : "";
  Promise.all([ensureSections().catch(() => {}), loadJson("history.json")])
    .then(([, list]) => {
      const box = $("historyBox");
      if (!Array.isArray(list) || !list.length) {
        box.innerHTML = '<div class="empty">暂无资费变化记录（首次基线已建立，后续检测到变更会自动记录）</div>';
        return;
      }
      box.innerHTML = '<div class="tl">' + list.map((r, idx) => {
        _histCache.set(r.ts, r);
        const entries = [];
        SECTIONS.forEach((secObj) => {
          const sec = secObj.section;
          if (filter && filter !== sec) return;
          const d = r[sec];
          if (!d || d.note === "baseline") return;
          const head = secName(sec);
          const chips = [];
          if (d.added) chips.push('<span class="chip add">新增 ' + d.added + "</span>");
          if (d.removed) chips.push('<span class="chip del">下架 ' + d.removed + "</span>");
          if (d.modified) chips.push('<span class="chip mod">修改 ' + d.modified + "</span>");
          if (!chips.length) chips.push('<span class="chip none">无变化</span>');
          // 所有板块（含湖南及其他各省）一并在历史区展示；无变化的省份也渲染并标注「无变化」
          entries.push(
            '<div class="tl-sec-entry' + (chips.length === 1 && chips[0].indexOf("none") >= 0 ? " nochange" : "") + '">' +
            '<div class="tl-sec-head" tabindex="0" role="button" aria-expanded="false">' +
            '<b>' + esc(head) + "</b>" +
            '<span class="tl-sec-chips">' + chips.join("") + "</span>" +
            '<span class="tl-sec-arrow"></span></div>' +
            '<div class="tl-sec-body">' + (histDetail(d, sec, r.ts) ||
              '<div class="tl-none">本次变化无明细条目</div>') + "</div></div>"
          );
        });
        if (!entries.length) {
          return (
            '<div class="tl-item"><div class="tl-time">' + esc(r.ts || "") + "</div>" +
            '<div class="tl-chips"><span class="chip">无变化</span></div></div>'
          );
        }
        const open = idx === list.length - 1; // 默认展开最新一条（展示各省摘要，各省明细默认收起）
        return (
          '<div class="tl-item' + (open ? " open" : "") + '" tabindex="0" role="button" aria-expanded="' + open + '">' +
          '<div class="tl-head"><div class="tl-time">' + esc(r.ts || "") + "</div><span class=\"tl-arrow\"></span></div>" +
          '<div class="tl-sec-list">' + entries.join("") + "</div></div>"
        );
      }).join("") + "</div>";

      box.querySelectorAll(".tl-item").forEach((item) => {
        const toggle = () => {
          const open = item.classList.toggle("open");
          item.setAttribute("aria-expanded", open ? "true" : "false");
        };
        item.addEventListener("click", (e) => {
          if (e.target.closest && e.target.closest("a")) return;
          toggle();
        });
        item.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
        });
        // 省份级折叠：点击省标题行，仅展开该省明细（捕获阶段 + stopPropagation 避免误触整条展开）
        item.querySelectorAll(".tl-sec-head").forEach((head) => {
          const toggleSec = () => {
            const entry = head.parentElement;
            const open = entry.classList.toggle("open");
            head.setAttribute("aria-expanded", open ? "true" : "false");
          };
          head.addEventListener("click", (e) => {
            if (e.target.closest && e.target.closest("a")) return;
            e.stopPropagation();
            toggleSec();
          }, true);
          head.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSec(); }
          });
        });
      });
    }).catch((e) => {
      $("historyBox").innerHTML = '<div class="empty">历史数据加载失败：' + esc(e.message) + "</div>";
    });
}

(function boot() {
  const raw = (location.hash || "").replace("#", "").trim();
  const valid = ["overview", "quanguo", "prov", "history", "about"].indexOf(raw) >= 0;
  goTab(valid ? raw : "overview");
})();

/* ---------- 检测资费 ---------- */
const RK = "gb_last_check";
const btnRefresh = $("refreshBtn");
function fetchNoCache(file) {
  return fetchTimeout(DATA + file, { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { delete cache[file]; return j; });
}
function openModal(title, html) { $("modalTitle").textContent = title; $("modalBody").innerHTML = html; $("modalMask").classList.add("show"); }
function closeModal() { $("modalMask").classList.remove("show"); $("modalMask").classList.remove("warn"); }

/* 切换运营商弹窗（75% 透明度，移动/联通/电信/广电导航） */
function openSwitch() { $("switchMask").classList.add("show"); }
function closeSwitch() { $("switchMask").classList.remove("show"); }
function initModal() {
  $("modalClose").addEventListener("click", closeModal);
  $("modalOk").addEventListener("click", closeModal);
  $("modalMask").addEventListener("click", (e) => { if (e.target === $("modalMask")) closeModal(); });
  $("switchBtn").addEventListener("click", openSwitch);
  $("switchClose").addEventListener("click", closeSwitch);
  $("switchMask").addEventListener("click", (e) => { if (e.target === $("switchMask")) closeSwitch(); });
}
function describeHistory(hist) {
  if (!Array.isArray(hist) || !hist.length) return "";
  const heads = SECTIONS.length ? SECTIONS : [{ section: "quanguo", name: "全网(全国)" }, { section: "hunan", name: "湖南" }];
  return hist.map((r) => {
    const t = esc(r.ts || "变更记录");
    const parts = [];
    heads.forEach((s) => {
      const d = r[s.section]; if (!d) return;
      const chips = [];
      if (d.added) chips.push('<span class="chip add">新增 ' + d.added + " 条</span>");
      if (d.removed) chips.push('<span class="chip del">下架 ' + d.removed + " 条</span>");
      if (d.modified) chips.push('<span class="chip mod">修改 ' + d.modified + " 条</span>");
      if (chips.length) parts.push('<div class="res-row"><b>' + esc(s.name) + "</b>：" + chips.join(" ") + "</div>");
    });
    return parts.length ? '<div class="res-hsev">' + t + parts.join("") + "</div>" : "";
  }).join("");
}
let checking = false;
function doCheck() {
  if (checking) return;
  checking = true;
  btnRefresh.classList.add("busy");
  const oldText = btnRefresh.textContent;
  btnRefresh.textContent = "检测中…";
  Promise.all([fetchNoCache("latest.json"), fetchNoCache("history.json")])
    .then(([latest, hist]) => {
      SECTIONS = latest.sections || SECTIONS;
      DEF_SECTION = latest.default || DEF_SECTION;
      if ($("pProv") && $("pProv").options.length === 0) fillProvSelects();
      const updated = (latest && latest.updated) || "";
      const hlen = Array.isArray(hist) ? hist.length : 0;
      let prev = null;
      try { prev = JSON.parse(localStorage.getItem(RK) || "null"); } catch (e) { prev = null; }
      const snap = { updated: updated, hlen: hlen };
      if (!prev) {
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("检测完成", '<div class="res-row">已建立首次检测基线。</div><div class="res-row sub">数据快照时间：' + esc(updated || "未知") + '</div><div class="res-row sub">历史变更记录：' + hlen + " 条</div>");
      } else if (hlen > (prev.hlen || 0)) {
        const newHist = Array.isArray(hist) ? hist.slice(prev.hlen || 0) : [];
        const detail = describeHistory(newHist) || '<div class="res-row">检测到资费变化，可到「变化历史」页查看详情。</div>';
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("检测到资费变化", detail + '<div class="res-row sub">快照时间：' + esc(updated || "未知") + "</div>");
      } else if (updated && prev.updated !== updated) {
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("数据快照已更新", '<div class="res-row">资费数据快照已更新，新增/下架条数为 0，可能为字段级微调。</div><div class="res-row sub">快照时间：' + esc(updated) + "</div>");
      } else {
        openModal("无变化", '<div class="res-row ok">暂未检测到资费变化。</div><div class="res-row sub">数据快照时间：' + esc(updated || "未知") + "</div>");
      }
      if ($("updateTime")) $("updateTime").textContent = "更新于 " + (updated || "未知");
    })
    .catch((e) => { openModal("检测失败", '<div class="res-row">数据获取失败：' + esc(e.message) + "</div>"); })
    .finally(() => { checking = false; btnRefresh.classList.remove("busy"); btnRefresh.textContent = oldText; });
}
initModal();
initProvPicker();

/* ---------- 通用单选筛选弹窗（搜索范围 / 类型 / 二级分类） ---------- */
let FP_SEL = null; // 当前弹窗关联的 select id
function fTitle(selId) {
  const sel = document.getElementById(selId);
  return (sel && sel.getAttribute("title")) || "选择";
}
function syncFPick(selId) {
  const btn = document.querySelector('.f-pick[data-fpick="' + selId + '"]');
  if (!btn) return;
  const sel = document.getElementById(selId);
  const s = (sel && sel.selectedIndex >= 0 && sel.options[sel.selectedIndex]) ? sel.options[sel.selectedIndex].text : "";
  btn.querySelector("span").textContent = s;
}
function openFPick(selId) {
  const sel = document.getElementById(selId); if (!sel) return;
  FP_SEL = selId;
  const list = document.getElementById("genList");
  const cur = sel.value;
  const items = Array.prototype.map.call(sel.options, (o, i) => {
    const on = o.value === cur;
    return '<button type="button" class="gen-item' + (on ? " on" : "") + '" data-i="' + i + '">' +
      "<span>" + esc(o.text) + '</span><span class="tick">✓</span></button>';
  }).join("");
  list.innerHTML = items || '<div class="gen-empty">暂无选项</div>';
  list.querySelectorAll(".gen-item").forEach((it) => {
    it.addEventListener("click", () => pickFPick(+it.dataset.i));
  });
  document.getElementById("genTitle").textContent = fTitle(selId);
  const b = document.querySelector('.f-pick[data-fpick="' + selId + '"]'); if (b) b.classList.add("open");
  document.getElementById("genMask").classList.add("show");
}
function pickFPick(idx) {
  const sel = document.getElementById(FP_SEL); if (!sel) return;
  sel.selectedIndex = idx;
  sel.dispatchEvent(new Event("change"));
  syncFPick(FP_SEL);
  closeFPick();
}
function closeFPick() {
  document.getElementById("genMask").classList.remove("show");
  if (FP_SEL) { const b = document.querySelector('.f-pick[data-fpick="' + FP_SEL + '"]'); if (b) b.classList.remove("open"); }
  FP_SEL = null;
}
function initFPick() {
  const c = document.getElementById("genClose"); if (c) c.addEventListener("click", closeFPick);
  const m = document.getElementById("genMask"); if (m) m.addEventListener("click", (e) => { if (e.target === m) closeFPick(); });
  document.querySelectorAll(".f-pick").forEach((btn) => {
    const selId = btn.dataset.fpick;
    btn.addEventListener("click", () => openFPick(selId));
    syncFPick(selId);
  });
}
initFPick();

/* 检测按钮点击频率限制：1 秒内点击超过 2 次，弹出 75% 透明度提示，本次不执行检测 */
const _clickStamp = [];
let _clickWarnTs = 0;
function btnRefreshGuard() {
  const now = Date.now();
  _clickStamp.push(now);
  while (_clickStamp.length && _clickStamp[0] <= now - 1000) _clickStamp.shift();
  if (_clickStamp.length > 2) {
    if (now - _clickWarnTs > 1000) {
      _clickWarnTs = now;
      $("modalMask").classList.add("warn");
      openModal("温馨提示",
        '<div class="res-row ok" style="text-align:center;font-size:15px;">操作过于频繁，请稍后再试</div>');
    }
    return false;
  }
  return true;
}
btnRefresh.addEventListener("click", () => { if (btnRefreshGuard()) doCheck(); });
/* ========== 按钮震动反馈（静音） ========== */
(function () {
  var TAPSEL2 = 'button, a, .tab, .btn, .glass-btn, .sort-btn, .refresh-btn, select, [role="button"]';
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target.closest(TAPSEL2) : null;
    if (!el) return;
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) {} }
  });
  // —— 其他说明折叠展开 ——
  // 用捕获阶段拦截：.notes-toggle 在列表项 .detail 内部，若走冒泡，
  // item 的 click 监听会先触发导致 detail 被误收起，故在捕获阶段即 stopPropagation
  document.addEventListener('click', function (e) {
    var tg = e.target && e.target.closest ? e.target.closest('.notes-toggle') : null;
    if (!tg) return;
    e.stopPropagation();
    var block = tg.closest('.notes-block');
    if (!block) return;
    var openNow = block.classList.toggle('open');
    tg.setAttribute('aria-expanded', openNow ? 'true' : 'false');
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) {} }
  }, true);
})();

/* ========== 更新公告弹窗（每个设备仅显示一次，几大站共用同一标记） ========== */
(function () {
  var KEY = "marvis_site_notice_20260911v2";
  var done = false;
  try { done = !!localStorage.getItem(KEY); } catch (e) {}
  if (done) return;
  var css = [
    ".notice-mask{position:fixed;inset:0;background:rgba(10,14,26,.55);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;animation:noticeFade .18s ease}",
    "@keyframes noticeFade{from{opacity:0}to{opacity:1}}",
    ".notice-card{background:#fff;border-radius:16px;max-width:400px;width:100%;overflow:hidden;box-shadow:0 14px 44px rgba(0,0,0,.28);font-size:14px;line-height:1.65;color:#222;box-sizing:border-box}",
    ".notice-top{background:linear-gradient(120deg,#6b4fa1,#a06ce0);color:#fff;padding:18px 20px 14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
    ".notice-ico{width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center;font-size:17px;flex:none}",
    ".notice-top h3{margin:0;font-size:16px;font-weight:600;flex:1;min-width:120px}",
    ".notice-top .notice-tag{font-size:11px;color:#fff;background:rgba(255,255,255,.25);border:1px solid rgba(255,255,255,.5);border-radius:10px;padding:2px 8px;font-weight:400}",
    ".notice-body{padding:16px 20px 6px}",
    ".notice-body p{margin:0 0 10px;color:#555}",
    ".notice-list{margin:0;padding:0;list-style:none}",
    ".notice-list li{position:relative;padding:4px 0 4px 22px;margin:0}",
    ".notice-list li:before{content:'✓';position:absolute;left:0;top:4px;color:#17a34a;font-weight:700}",
    ".notice-ft{padding:12px 20px 18px;text-align:right}",
    ".notice-ok{border:0;background:linear-gradient(120deg,#6b4fa1,#a06ce0);color:#fff;font-size:14px;padding:9px 26px;border-radius:20px;cursor:pointer;font-weight:500;box-shadow:0 4px 12px rgba(0,0,0,.14)}",
    ".notice-ok:active{opacity:.85}",
    "body.dark .notice-card{background:#171c28;color:#e6e8ee}",
    "body.dark .notice-top{filter:brightness(.9)}",
    "body.dark .notice-body p{color:#b9bfcc}"
  ].join(" ");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  var card = document.createElement("div");
  card.className = "notice-card";
  card.innerHTML =
    '<div class="notice-top"><span class="notice-ico">📢</span><h3>资费站更新公告</h3><span class="notice-tag">2026.09.11</span></div>' +
    '<div class="notice-body"><p>本次更新主要内容：</p><ul class="notice-list">' +
    "<li>优化了资费文字排版，查看更清晰。</li>" +
    "<li>新增广电运营商站点，四大运营商一站切换。</li>" +
    "<li>美化省份选择弹窗，顶部固定搜索栏。</li>" +
    "<li>搜索支持「全局 / 仅业务名称」范围切换。</li>" +
    '</ul></div>' +
    '<div class="notice-ft"><button class="notice-ok" id="notice-ok-btn">知道了</button></div>';
  var mask = document.createElement("div");
  mask.className = "notice-mask";
  mask.appendChild(card);
  document.body.appendChild(mask);
  var ok = document.getElementById("notice-ok-btn");
  if (ok) {
    ok.addEventListener("click", function () {
      try { localStorage.setItem(KEY, "1"); } catch (e) {}
      if (mask && mask.parentNode) mask.parentNode.removeChild(mask);
    });
  }
})();

