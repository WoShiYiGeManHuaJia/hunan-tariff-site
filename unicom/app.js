/* 中国联通资费专区 - 前端逻辑（vlt20260904：全功能对齐移动站，31省切换/变化历史/总览联动） */
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
const PROV_KEY = "lt_selected_prov";
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
      listState.prov = null;
      renderList("prov");
    });
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
      renderProvPanel();
    });
  }
  const hfEl = $("hProvFilter");
  if (hfEl && hfEl.options.length === 0) {
    let hopts = '<option value="">全部省份</option>';
    hopts += provList().map((s) => '<option value="' + esc(s.section) + '">' + esc(s.name) + "</option>").join("");
    hfEl.innerHTML = hopts;
    hfEl.addEventListener("change", () => renderHistory());
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
    document.title = "中国联通资费专区 · 更新于 " + (d.updated || "");
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
  $("distDesc").textContent = name + "口径 · 六大类分布";
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

const LT_LABELS = ["套餐", "加装包", "营销活动", "标准资费", "港澳台/国际资费", "停售套餐"];
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
function getSt(section) {
  if (!listState[section]) listState[section] = { items: null, page: 1, q: "", type: "", sub: "" };
  return listState[section];
}
function domMap(section) {
  if (section === "quanguo") {
    return { list: "qList", pager: "qPager", cnt: "qCount", search: "qSearch", type: "qType", sub: "qSub", reload: "qReload" };
  }
  return { list: "pList", pager: "pPager", cnt: "pCount", search: "pSearch", type: "pType", sub: "pSub", reload: "pReload" };
}

const TYPE_FIRST = { "套餐": 1, "加装包": 1, "营销活动": 1, "标准资费": 1, "港澳台/国际资费": 1, "停售套餐": 1 };
function firstLevelOf(it) { return it.firstLevel || "其他"; }
function secondLevelOf(it) { return it.secondLevel || "其他"; }

function renderList(section) {
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
    if (section !== "quanguo") { $("pProv").value = (provList().some((s) => s.section === section) ? section : $("pProv").value); }
    drawList(section);
  }).catch((e) => { listEl.innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>"; });

  if (!qEl.dataset.bound) {
    qEl.dataset.bound = "1";
    qEl.addEventListener("input", () => { st.q = qEl.value.trim().toLowerCase(); st.page = 1; drawList(section); });
    const typeEl = $(idm.type);
    const subEl = $(idm.sub);
    if (typeEl) typeEl.addEventListener("change", () => { st.type = typeEl.value; st.page = 1; drawList(section); });
    if (subEl) subEl.addEventListener("change", () => { st.sub = subEl.value; st.page = 1; drawList(section); });
    $(idm.reload).addEventListener("click", () => { st.items = null; renderList(section); });
  }
}

function filterItems(st) {
  const src = st.items || [];
  const out = [];
  for (const it of src) {
    if (st.type) {
      const sub = firstLevelOf(it);
      if (sub === "停售套餐") { if (st.type !== "停售套餐") continue; }
      else if (sub !== st.type) continue;
    }
    if (st.sub && secondLevelOf(it) !== st.sub) continue;
    if (st.q) {
      const d = it.detail || {};
      const hay = [it.title, it.fee, d.feesStandard, d.serviceContent, d.useScope, d.codeType,
        firstLevelOf(it), secondLevelOf(it)].filter((v) => v != null && v !== "").join(" ").toLowerCase();
      if (!hay.includes(st.q)) continue;
    }
    out.push(it);
  }
  return out;
}

function drawList(section) {
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
  }
  const filtered = filterItems(st);
  filtered.sort((a, b) => {
    const aStop = firstLevelOf(a) === "停售套餐" ? 1 : 0;
    const bStop = firstLevelOf(b) === "停售套餐" ? 1 : 0;
    if (aStop !== bStop) return aStop - bStop;
    const af = parseFloat(a.fee), bf = parseFloat(b.fee);
    if (isNaN(af)) return 1; if (isNaN(bf)) return -1;
    return af - bf;
  });
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
  const mainKeys = ["资费类型", "月费标准", "语音", "流量", "短信", "定向流量", "宽带", "套餐内容", "适用对象", "有效期", "其他收费", "办理渠道", "停售状态"];
  const rows = detailRows(it);
  const filteredRows = rows.filter(([k]) => mainKeys.indexOf(k) >= 0).map(([k, v]) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(v) + "</td></tr>").join("");
  const otherRows = rows.filter(([k]) => mainKeys.indexOf(k) < 0).map(([k, v]) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(v) + "</td></tr>").join("");
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
      '<div class="detail"><table>' + filteredRows + otherRows + '</table></div>' +
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
    ["办理渠道", d.saleChnl || "-"],
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
  [["added", "add", "新增", false], ["removed", "del", "下架", false], ["modified", "mod", "修改", true]].forEach(([key, cls, lab, clickable]) => {
    const n = d[key] || 0;
    if (!n) return;
    html += '<div class="tl-sec"><span class="chip ' + cls + '">' + lab + " " + n + " 条</span>";
    const names = Array.isArray(d[key + "_names"]) ? d[key + "_names"] : null;
    if (names && names.length) {
      if (clickable) {
        // 修改业务：可点击查看字段级修改明细
        html += '<ul class="tl-names">' + names.map((x) =>
          '<li><a class="tl-mod" href="javascript:void(0)" ' +
          'data-ts="' + aesc(ts) + '" data-sec="' + aesc(sec) + '" data-name="' + aesc(x) + '" ' +
          'title="点击查看该业务的修改明细" ' +
          'onclick="event.stopPropagation();showModDetail(this.dataset.ts,this.dataset.sec,this.dataset.name)">' +
          esc(x) + "</a>" +
          (d.modified_details && d.modified_details[x] ? '<span class="mod-badge">查看明细</span>' : "") +
          "</li>"
        ).join("") + "</ul>";
      } else {
        html += '<ul class="tl-names">' + names.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul>";
      }
    } else {
      html += '<div class="tl-none">本次' + lab + " " + n + " 条，可在对应资费列表查看</div>";
    }
    html += "</div>";
  });
  return html;
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
    const pv = esc(dt.from || "（空）");
    const nv = esc(dt.to || "（空）");
    return '<div class="mod-row">' +
      '<div class="mod-f">' + pf + "</div>" +
      '<div class="mod-v">' +
      '<div class="mod-old" title="修改前">' + pv + "</div>" +
      '<div class="mod-arrow">→</div>' +
      '<div class="mod-new" title="修改后">' + nv + "</div>" +
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
        const parts = [];
        const details = [];
        SECTIONS.forEach((secObj) => {
          const sec = secObj.section;
          if (filter && filter !== sec) return;
          const d = r[sec];
          if (!d || d.note === "baseline") return;
          const chips = [];
          if (d.added) chips.push('<span class="chip add">新增 ' + d.added + "</span>");
          if (d.removed) chips.push('<span class="chip del">下架 ' + d.removed + "</span>");
          if (d.modified) chips.push('<span class="chip mod">修改 ' + d.modified + "</span>");
          if (chips.length) {
            parts.push("<div><b>" + esc(secName(sec)) + "</b>：" + chips.join("") + "</div>");
            const detail = histDetail(d, sec, r.ts);
            if (detail) details.push('<div class="tl-sec-title">' + esc(secName(sec)) + "</div>" + detail);
          }
        });
        if (!parts.length) {
          return '<div class="tl-item"><div class="tl-time">' + esc(r.ts || "") + '</div><div class="tl-chips"><span class="chip">无变化</span></div></div>';
        }
        const open = idx === list.length - 1;
        return (
          '<div class="tl-item' + (open ? " open" : "") + '" tabindex="0" role="button" aria-expanded="' + open + '">' +
          '<div class="tl-head"><div class="tl-time">' + esc(r.ts || "") + "</div><span class=\"tl-arrow\"></span></div>" +
          '<div class="tl-chips">' + parts.join("") + "</div>" +
          '<div class="tl-body">' + details.join("") + "</div></div>"
        );
      }).join("") + "</div>";
      box.querySelectorAll(".tl-item").forEach((item) => {
        const toggle = () => { const open = item.classList.toggle("open"); item.setAttribute("aria-expanded", open ? "true" : "false"); };
        item.addEventListener("click", (e) => { if (e.target.closest && e.target.closest("a")) return; toggle(); });
        item.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
      });
    }).catch((e) => { $("historyBox").innerHTML = '<div class="empty">历史数据加载失败：' + esc(e.message) + "</div>"; });
}

(function boot() {
  const raw = (location.hash || "").replace("#", "").trim();
  const valid = ["overview", "quanguo", "prov", "history", "about"].indexOf(raw) >= 0;
  goTab(valid ? raw : "overview");
})();

/* ---------- 检测资费 ---------- */
const RK = "lt_last_check";
const btnRefresh = $("refreshBtn");
function fetchNoCache(file) {
  return fetchTimeout(DATA + file, { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { delete cache[file]; return j; });
}
function openModal(title, html) { $("modalTitle").textContent = title; $("modalBody").innerHTML = html; $("modalMask").classList.add("show"); }
function closeModal() { $("modalMask").classList.remove("show"); $("modalMask").classList.remove("warn"); }
function initModal() {
  $("modalClose").addEventListener("click", closeModal);
  $("modalOk").addEventListener("click", closeModal);
  $("modalMask").addEventListener("click", (e) => { if (e.target === $("modalMask")) closeModal(); });
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
function doCheck() {
  btnRefresh.disabled = true;
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
    .finally(() => { btnRefresh.disabled = false; btnRefresh.textContent = oldText; });
}
initModal();

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
