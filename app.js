/* 中国移动资费监控面板 - 前端逻辑（v20260911c：排序条新增「零元业务」筛选；0元每月/免费在前、0元每次在后；保留按钮震动、无声音） */
"use strict";
const DATA = "./data/";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
  {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
));
const cache = {};

/* ---------- 适用地区：4位数字码 -> 地市名（码 = 区号规则，如 5760 -> 台州） ---------- */
const AREA_CODE_MAP = {
"0100":"北京", "0200":"广州", "0210":"上海", "0220":"天津",
"0230":"重庆", "0240":"沈阳", "0250":"南京", "0270":"武汉",
"0280":"成都", "0290":"西安", 3100:"邯郸", 3110:"石家庄",
3120:"保定", 3130:"张家口", 3140:"承德", 3150:"唐山",
3160:"廊坊", 3170:"沧州", 3180:"衡水", 3190:"邢台",
3350:"秦皇岛", 3490:"朔州", 3500:"忻州", 3510:"太原",
3520:"大同", 3530:"阳泉", 3540:"晋中", 3550:"长治",
3560:"晋城", 3570:"临汾", 3580:"吕梁", 3590:"运城",
3700:"商丘", 3710:"郑州", 3720:"安阳", 3730:"新乡",
3740:"许昌", 3750:"平顶山", 3760:"信阳", 3770:"南阳",
3790:"洛阳", 3910:"焦作", 3920:"鹤壁", 3930:"濮阳",
3940:"周口", 3950:"漯河", 3960:"驻马店", 3980:"三门峡",
4100:"铁岭", 4110:"大连", 4120:"鞍山", 4130:"抚顺",
4140:"本溪", 4150:"丹东", 4160:"锦州", 4170:"营口",
4180:"阜新", 4190:"辽阳", 4210:"朝阳", 4270:"盘锦",
4290:"葫芦岛", 4310:"长春", 4320:"吉林", 4330:"延边",
4340:"四平", 4350:"通化", 4360:"白城", 4370:"辽源",
4380:"松原", 4390:"白山", 4510:"哈尔滨", 4520:"齐齐哈尔",
4530:"牡丹江", 4540:"佳木斯", 4550:"绥化", 4560:"黑河",
4570:"大兴安岭", 4580:"伊春", 4590:"大庆", 4640:"七台河",
4670:"鸡西", 4680:"鹤岗", 4690:"双鸭山", 4700:"呼伦贝尔",
4710:"呼和浩特", 4720:"包头", 4730:"乌海", 4740:"乌兰察布",
4750:"通辽", 4760:"赤峰", 4770:"鄂尔多斯", 4780:"巴彦淖尔",
4790:"锡林郭勒", 4820:"兴安盟", 4830:"阿拉善", 5100:"无锡",
5110:"镇江", 5120:"苏州", 5130:"南通", 5140:"扬州",
5150:"盐城", 5160:"徐州", 5170:"淮安", 5180:"连云港",
5190:"常州", 5230:"泰州", 5270:"宿迁", 5300:"菏泽",
5310:"济南", 5320:"青岛", 5330:"淄博", 5340:"德州",
5350:"烟台", 5360:"潍坊", 5370:"济宁", 5380:"泰安",
5390:"临沂", 5430:"滨州", 5460:"东营", 5500:"滁州",
5510:"合肥", 5520:"蚌埠", 5530:"芜湖", 5540:"淮南",
5550:"马鞍山", 5560:"安庆", 5570:"宿州", 5580:"阜阳",
5590:"黄山", 5610:"淮北", 5620:"铜陵", 5630:"宣城",
5640:"六安", 5660:"池州", 5700:"衢州", 5710:"杭州",
5720:"湖州", 5730:"嘉兴", 5740:"宁波", 5750:"绍兴",
5760:"台州", 5770:"温州", 5780:"丽水", 5790:"金华",
5800:"舟山", 5910:"福州", 5920:"厦门", 5930:"宁德",
5940:"莆田", 5950:"泉州", 5960:"漳州", 5970:"龙岩",
5980:"三明", 5990:"南平", 6310:"威海", 6320:"枣庄",
6330:"日照", 6350:"聊城", 6600:"汕尾", 6620:"阳江",
6630:"揭阳", 6680:"茂名", 6910:"西双版纳", 6920:"德宏",
7010:"鹰潭", 7100:"襄阳", 7110:"鄂州", 7120:"孝感",
7130:"黄冈", 7140:"黄石", 7150:"咸宁", 7160:"荆州",
7170:"宜昌", 7180:"恩施", 7190:"十堰", 7220:"随州",
7240:"荆门", 7300:"岳阳", 7310:"长沙", 7340:"衡阳",
7350:"郴州", 7360:"常德", 7370:"益阳", 7380:"娄底",
7390:"邵阳", 7430:"湘西", 7440:"张家界", 7450:"怀化",
7460:"永州", 7500:"江门", 7510:"韶关", 7520:"惠州",
7530:"梅州", 7540:"汕头", 7550:"深圳", 7560:"珠海",
7570:"佛山", 7580:"肇庆", 7590:"湛江", 7600:"中山",
7620:"河源", 7630:"清远", 7660:"云浮", 7680:"潮州",
7690:"东莞", 7700:"防城港", 7710:"崇左", 7720:"来宾",
7730:"桂林", 7740:"梧州", 7750:"贵港", 7760:"百色",
7770:"钦州", 7780:"河池", 7790:"北海", 7900:"新余",
7910:"南昌", 7920:"九江", 7930:"上饶", 7940:"抚州",
7950:"宜春", 7960:"吉安", 7970:"赣州", 7980:"景德镇",
7990:"萍乡", 8120:"攀枝花", 8130:"自贡", 8160:"绵阳",
8170:"南充", 8180:"达州", 8250:"遂宁", 8260:"广安",
8270:"巴中", 8300:"泸州", 8310:"宜宾", 8320:"内江",
8330:"乐山", 8340:"凉山", 8350:"雅安", 8380:"德阳",
8390:"广元", 8510:"贵阳", 8520:"遵义", 8530:"安顺",
8540:"黔南", 8550:"黔东南", 8560:"铜仁", 8570:"毕节",
8580:"六盘水", 8590:"黔西南", 8700:"昭通", 8710:"昆明",
8720:"大理", 8730:"红河", 8740:"曲靖", 8750:"保山",
8760:"文山", 8770:"玉溪", 8780:"楚雄", 8790:"普洱",
8830:"临沧", 8860:"怒江", 8870:"迪庆", 8880:"丽江",
8910:"拉萨", 8920:"日喀则", 8930:"山南", 8940:"林芝",
8950:"昌都", 8960:"那曲", 8970:"阿里", 8980:"海南",
9010:"塔城", 9020:"哈密", 9030:"和田", 9060:"阿勒泰",
9080:"克孜勒苏", 9090:"博尔塔拉", 9100:"咸阳", 9110:"延安",
9120:"榆林", 9130:"渭南", 9140:"商洛", 9150:"安康",
9160:"汉中", 9170:"宝鸡", 9190:"铜川", 9300:"临夏",
9310:"兰州", 9320:"定西", 9330:"平凉", 9340:"庆阳",
9350:"金昌", 9360:"张掖", 9370:"嘉峪关", 9380:"天水",
9390:"陇南", 9410:"甘南", 9430:"白银", 9510:"银川",
9520:"石嘴山", 9530:"吴忠", 9540:"固原", 9550:"中卫",
9700:"海北", 9710:"西宁", 9720:"海东", 9730:"黄南",
9740:"海南", 9750:"果洛", 9760:"玉树", 9770:"海西",
9900:"克拉玛依", 9910:"乌鲁木齐", 9930:"石河子", 9940:"昌吉",
9950:"吐鲁番", 9960:"巴音郭楞", 9970:"阿克苏", 9980:"喀什",
9990:"伊犁",
};
/* 适用地区字段：4位数字码 -> 地名；000 -> 全国；多码逗号/顿号分隔逐个转换；无法识别的码原样返回 */
function areaFallback(p) {
  if (AREA_CODE_MAP[p]) return AREA_CODE_MAP[p];
  if (p && p.length === 4 && /^\d{4}$/.test(p)) {
    const t = p.slice(0, 3) + "0"; // 尾码回退：0241/0242 等子码 -> 该区号城市
    if (AREA_CODE_MAP[t]) return AREA_CODE_MAP[t];
  }
  return p;
}
function areaCn(v) {
  if (v == null) return v;
  v = String(v).trim();
  if (!v) return v;
  if (/^0{2,4}$/.test(v)) return "全国";
  if (/^[\d,，、\s]+$/.test(v)) {
    const parts = v.split(/[,，、\s]+/).map((s) => s.trim()).filter(Boolean);
    if (parts.length > 1) return parts.map(areaFallback).join("、");
  }
  return areaFallback(v);
}

const FETCH_TIMEOUT = 20000; // 20s 超时，避免弱网下无限“加载中”卡死
function fetchTimeout(url, init) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT);
  return fetch(url, Object.assign({}, init || {}, { signal: ctrl.signal }))
    .catch((e) => {
      if (e && e.name === "AbortError") throw new Error("加载超时，请检查网络后重试");
      throw e;
    })
    .finally(() => clearTimeout(t));
}

function loadJson(file) {
  if (cache[file]) return Promise.resolve(cache[file]);
  return fetchTimeout(DATA + file)
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { cache[file] = j; return j; });
}

/* ---------- 公告数据（announce.json，最新15条） ---------- */
let announceCache = null;
function loadAnnounce() {
  if (announceCache) return Promise.resolve(announceCache);
  return fetchTimeout(DATA + "announce.json")
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { announceCache = j; return j; })
    .catch((e) => { announceCache = null; throw e; });
}

/* ---------- 板块索引：SECTIONS / 省份列表（来自 latest.json） ---------- */
let SECTIONS = [];        // [{section,name,total,updated}]
let DEF_SECTION = "hunan"; // 默认省份
const PROV_KEY = "trf_selected_prov";

function provList() {
  return SECTIONS.filter((s) => s.section !== "quanguo");
}
function secName(sec) {
  const s = SECTIONS.find((x) => x.section === sec);
  return s ? s.name : sec;
}

/* 加载 latest.json 并填充省份下拉（幂等，只填一次） */
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

initProvPicker();

/* ---------- 通用单选筛选弹窗（搜索范围 / 归属 / 类型 / 二级分类） ---------- */
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

/* ---------- Tab 切换（支持 hash 直达，如 #history / #prov） ---------- */
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
  else if (v === "announce") renderAnnounce();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    goTab(tab.dataset.view);
    try { history.replaceState(null, "", "#" + tab.dataset.view); } catch (e) {}
  });
});

/* ---------- 数据总览 ---------- */
let LATEST = null; // 最近一次 latest.json（省份面板联动直接读内存，不重复请求）
function renderOverview() {
  loadJson("latest.json").then((d) => {
    LATEST = d;
    SECTIONS = d.sections || [];
    DEF_SECTION = d.default || DEF_SECTION;
    fillProvSelects();
    $("stTotal").textContent = (d.quanguo_total == null) ? "-" : fmt(d.quanguo_total);
    $("stAllProv").textContent = (d.prov_total == null) ? "-" : fmt(d.prov_total);
    $("updateTime").textContent = "更新于 " + (d.updated || "未知");
    document.title = "中国移动资费监控 · 更新于 " + (d.updated || "");
    renderProvPanel();   // 顶部个人/政企卡 + 省份面板统一按所选省份联动（不必再渲染全网口径）
  }).catch((e) => {
    $("stTotal").textContent = "加载失败";
    $("updateTime").textContent = "加载失败";
    $("distBars").innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
}
function fmt(n) { return (n === undefined || n === null) ? "-" : n.toLocaleString("zh-CN"); }
function confStat(el, cur) {
  el.innerHTML = (cur == null) ? "-" : fmt(cur);
}

/* 总览页顶部「个人/政企」卡 + 「省份资费统计」面板：全部随 oProv 下拉切换实时联动 */
function renderProvPanel() {
  const provEl = $("oProv");
  if (!provEl) return;
  if (!provEl.options.length) fillProvSelects();
  const sec = provEl.value || DEF_SECTION;
  const st = (LATEST && LATEST.prov_stats) ? (LATEST.prov_stats[sec] || null) : null;
  const name = secName(sec);
  $("opLabel").textContent = name + "资费总数";
  $("stQuanguoLabel").textContent = name + "个人资费";
  $("stGqLabel").textContent = name + "政企资费";
  $("distDesc").textContent = name + "口径 · 六大类分布";
  if (!st) {
    confStat($("opTotal"), null);
    confStat($("stQuanguo"), null);
    confStat($("stGq"), null);
    $("distBars").innerHTML = '<div class="empty">暂无该省统计</div>';
    return;
  }
  confStat($("opTotal"), st.total);
  confStat($("stQuanguo"), st.personal);
  confStat($("stGq"), st.gq);
  renderBarsBox($("distBars"), st.dist || {});
}

function renderBarsBox(box, dist) {
  if (!box) return;
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

/* ---------- 列表（全国 / 省份） ---------- */
const PAGE_SIZE = 20;
const listState = {};    // section -> {items,page,q,own,type}
function liveSec() {
  const el = document.getElementById("pProv");
  return (el && el.value) || DEF_SECTION;
}
function getSt(section) {
  if (!listState[section]) listState[section] = { items: null, page: 1, q: "", scope: "all", own: "", type: "", sort: null, order: null };
  return listState[section];
}
function domMap(section) {
  if (section === "quanguo") {
    return { list: "qList", pager: "qPager", cnt: "qCount", search: "qSearch", scope: "qScope", own: "qOwn", type: "qType", reload: "qReload" };
  }
  return { list: "pList", pager: "pPager", cnt: "pCount", search: "pSearch", scope: "pScope", own: "pOwn", type: "pType", reload: "pReload" };
}

function renderList(section) {
  // "prov" 为省份 tab 的占位 section，需解析为下拉当前所选省份（data/ 下按省份文件名存储）
  const rawKey = section; // 原始视图键：quanguo / prov（用于定位排序条）
  if (section === "prov") { section = ((document.getElementById("pProv") || {}).value || "hunan"); }
  if (section !== "quanguo") { ensureSections(); }
  const st = getSt(section);
  const idm = domMap(section);
  const listEl = $(idm.list);
  const file = section === "quanguo" ? "quanguo.json" : section + ".json";
  const label = section === "quanguo" ? "全国" : (secName(section) || section);
  const qEl = $(idm.search);
  if (!st.items) {
    listEl.innerHTML = '<div class="loading">加载' + esc(label) + "资费数据（约 2MB，请稍候）…</div>";
  }
  loadJson(file).then((d) => {
    st.items = d.items || [];
    $("updateTime").textContent = "更新于 " + (d.timestamp || "未知");
    if (section !== "quanguo") { $("pProv").value = (provList().some((s) => s.section === section) ? section : $("pProv").value); }
    drawList(section);
  }).catch((e) => {
    listEl.innerHTML = '<div class="empty">数据加载失败：' + esc(e.message) + "</div>";
  });
  // 绑定筛选控件（同一 DOM 只绑一次；省份切换不重复绑定，仅更新数据缓存）
  if (!qEl.dataset.bound) {
    const secOf = () => (rawKey === "quanguo" ? "quanguo" : liveSec());
    const stOf = () => getSt(secOf());
    qEl.dataset.bound = "1";
    qEl.addEventListener("input", () => { const st = stOf(); st.q = qEl.value.trim().toLowerCase(); st.page = 1; drawList(secOf()); });
    const scopeEl = idm.scope ? $(idm.scope) : null;
    if (scopeEl) scopeEl.addEventListener("change", () => { const st = stOf(); st.scope = scopeEl.value; st.page = 1; drawList(secOf()); });
    const ownEl = idm.own ? $(idm.own) : null;
    const typeEl = $(idm.type);
    if (ownEl) ownEl.addEventListener("change", () => { const st = stOf(); st.own = ownEl.value; st.page = 1; drawList(secOf()); });
    if (typeEl) typeEl.addEventListener("change", () => { const st = stOf(); st.type = typeEl.value; st.page = 1; drawList(secOf()); });
    $(idm.reload).addEventListener("click", () => { const st = stOf(); st.items = null; renderList(secOf()); });
    setupSortBar(rawKey);
  }
}

/* ---------- 资费排序（最新上架 / 价格 / 方向） ---------- */
function timeOf(it) {
  const f = it.fields || {};
  const s = f["上线日期"] || "";
  if (s) {
    const m = s.match(/20\d{2}\D+(\d{1,2})\D+(\d{1,2})/);
    if (m) { const y = s.match(/20\d{2}/)[0]; return new Date(+y, (+m[1]) - 1, +m[2]).getTime(); }
  }
  const vp = f["有效期限"] || "";
  const vm = vp.match(/20\d{2}/);
  return vm ? new Date(+vm[0], 0, 1).getTime() : 0;
}
function priceOf(it) {
  const f = it.fields || {};
  const raw = f["资费标准"] || "";
  const m = String(raw).match(/\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : 0;
}
/* ---- 零元业务：筛选当前省份/全国中费用为 0 的资费；0元每月/免费在前、0元每次在后 ---- */
function isZeroFee(it) {
  const f = it.fields || {};
  const raw = String(f["资费标准"] || "");
  if (/免费/.test(raw)) return true;
  const m = raw.match(/\d+(?:\.\d+)?/);
  return !!m && Math.abs(parseFloat(m[0])) < 1e-9;
}
function zeroRank(it) {
  const f = it.fields || {};
  const raw = String(f["资费标准"] || "");
  if (/次/.test(raw)) return 2;                 // 0元/次 → 后排
  if (/月/.test(raw) || /免费/.test(raw)) return 0; // 0元/月、免费 → 前排
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
    if (st.own && (it.fields && it.fields["归属"]) !== st.own) continue;
    if (st.type && (it.fields && it.fields["资费类型"]) !== st.type) continue;
    if (st.q) {
      if (st.scope === "name") {
        if ((it.name || "").toLowerCase().indexOf(st.q) < 0) continue;
      } else {
        const f = it.fields || {};
        const vals = Object.values(f).filter((v) => v != null && v !== "").join(" ");
        const hay = (it.name + " " + vals).toLowerCase();
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
  const filtered = filterItems(st);
  if (st.zero) { filtered.sort(function (a, b) { return zeroRank(a) - zeroRank(b); }); }
  else if (st.sort) { sortFiltered(filtered, st); }
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

function fieldsTable(f) {
  f = f || {};
  const keys = Object.keys(f);
  const mainKeys = ["资费标准", "方案编号", "资费类型", "归属", "适用范围", "适用地区", "上线日期", "下线日期", "有效期限",
                    "在网要求", "退订方式", "违约责任", "销售渠道"];
  // 官方「其他说明」与 超出资费说明/其他服务内容/权益 统一收进「其他说明」折叠，避免主表摊开大段说明
  const noteKeys = ["其他说明", "超出资费说明", "其他服务内容", "权益"];
  const detailRows = mainKeys.filter((k) => f[k]).map((k) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(k === "适用地区" ? areaCn(f[k]) : f[k]) + "</td></tr>"
  ).join("");
  const otherRows = keys.filter((k) => !mainKeys.includes(k) && !noteKeys.includes(k) && f[k]).map((k) =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(k === "适用地区" ? areaCn(f[k]) : f[k]) + "</td></tr>"
  ).join("");
  let html = '<table>' + detailRows + otherRows + '</table>';
  // 其他说明折叠块（超出资费说明 / 其他服务内容）
  const noteHtml = noteKeys.filter((k) => f[k]).map((k) =>
    '<div class="note-item"><div class="note-label">' + esc(k) + "</div>" +
    '<div class="note-text">' + esc(f[k]) + "</div></div>"
  ).join("");
  if (noteHtml) {
    html +=
      '<div class="notes-block">' +
        '<div class="notes-toggle" role="button" tabindex="0" aria-expanded="false">其他说明' +
        '<span class="notes-arrow"></span></div>' +
        '<div class="notes-body">' + noteHtml + "</div>" +
      "</div>";
  }
  return html;
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
  return (
    '<div class="item">' +
      '<div class="item-head">' +
        '<span class="item-name">' + esc(it.name) + "</span>" +
        (own ? '<span class="tag ' + (own.indexOf("政企") >= 0 ? "own-gq" : "") + '">' + esc(own) + "</span>" : "") +
        (type ? '<span class="tag ' + (type === "加装包" ? "type-jz" : type === "营销活动" ? "type-yx" : "") + '">' + esc(type) + "</span>" : "") +
        (price ? '<span class="tag">' + esc(price) + "</span>" : "") +
      "</div>" +
      (facts.length ? '<div class="item-facts">' + facts.join("") + "</div>" : "") +
      '<div class="detail">' + fieldsTable(f) + "</div>" +
    "</div>"
  );
}

/* ---------- 变化历史（按省份分组 + 筛选） ---------- */
const _histCache = new Map();   // ts -> 历史记录对象，供「修改业务」明细弹窗查询
function aesc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;"); }

function histDetail(d, sec, ts) {
  if (!d || typeof d !== "object") return "";
  let html = "";
  const kinds = [
    ["added", "add", "新增", "showAddDetail"],
    ["removed", "del", "下架", "showDelDetail"],
    ["modified", "mod", "修改", "showModDetail"],
  ];
  kinds.forEach(([key, cls, lab, fn]) => {
    const n = d[key] || 0;
    if (!n) return;
    html += '<div class="tl-sec"><span class="chip ' + cls + '">' + lab + " " + n + " 条</span>";
    const names = Array.isArray(d[key + "_names"]) ? d[key + "_names"] : null;
    if (names && names.length) {
      if (fn) {
        // 新增/修改业务：可点击查看详情（新增看完整配置，修改看字段级明细）
        const dk = d[key + "_details"];
        html += '<ul class="tl-names">' + names.map((x) =>
          '<li class="tl-k ' + cls + '"><a class="tl-mod" href="javascript:void(0)" ' +
          'data-ts="' + aesc(ts) + '" data-sec="' + aesc(sec) + '" data-name="' + aesc(x) + '" ' +
          'title="点击查看该业务详情" ' +
          'onclick="event.stopPropagation();' + fn + '(this.dataset.ts,this.dataset.sec,this.dataset.name)">' +
          esc(x) + "</a>" +
          (dk && dk[x] ? '<span class="mod-badge">查看详情</span>' : "") +
          "</li>"
        ).join("") + "</ul>";
      } else {
        html += '<ul class="tl-names">' + names.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul>";
      }
    } else {
      html += '<div class="tl-none">本次' + lab + " " + n + " 条，名称未记录，可在对应资费列表查看</div>";
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
    const normV = (v) => (typeof v === "string" ? (/^0{2,}$/.test(v) ? "全国（不限定省份）" : areaCn(v)) : v);
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

/* 新增业务明细弹窗：展示该业务新增时的完整配置（字段表格） */
function showAddDetail(ts, sec, name) {
  const head = '<div class="res-row sub">变更时间：' + esc(ts) + " · " + esc(secName(sec)) + "</div>";
  const renderFields = (f) => {
    if (!f || !Object.keys(f).length) {
      openModal(name, head + '<div class="res-row">该记录未保存新增业务完整配置。</div>' +
        '<div class="res-row sub">可在「' + esc(secName(sec)) + '资费」列表查看该业务当前配置。</div>');
      return;
    }
    openModal(name, head +
      '<div class="res-row sub">该业务本次新增，完整配置如下：</div>' +
      '<div class="mod-diff">' + fieldsTable(f) + "</div>");
  };
  // 优先读历史记录中保存的新增时字段快照
  const rec = _histCache.get(ts);
  const d = rec ? rec[sec] : null;
  const snap = (d && d.added_details && d.added_details[name]) || null;
  if (snap) { renderFields(snap); return; }
  // 兜底：从当前板块数据按名称查找该业务字段
  const file = sec === "quanguo" ? "quanguo.json" : sec + ".json";
  loadJson(file).then((j) => {
    const items = (j && j.items) || [];
    const nm = String(name == null ? "" : name).trim();
    const it = items.find((x) => x && String(x.name || "").trim() === nm);
    renderFields(it ? (it.fields || {}) : null);
  }).catch((e) => {
    openModal(name, head + '<div class="res-row">加载详情失败：' + esc(e.message) + "</div>");
  });
}

/* 下架业务详情弹窗：历史页「下架」可点开，展示下架时保存的字段快照。
   无快照时提示已下架（线上板块已无该业务，无法再查）。 */
function showDelDetail(ts, sec, name) {
  const head = '<div class="res-row sub">变更时间：' + esc(ts) + " · " + esc(secName(sec)) + "</div>";
  const rec = _histCache.get(ts);
  const d = rec ? rec[sec] : null;
  const snap = (d && d.removed_details && d.removed_details[name]) || null;
  if (snap && Object.keys(snap).length) {
    openModal(name, head +
      '<div class="res-row sub">该业务本次下架，下架时配置如下：</div>' +
      '<div class="mod-diff">' + fieldsTable(snap) + "</div>");
    return;
  }
  openModal(name, head + '<div class="res-row">该套餐已从板块下架，线上无剩余配置可查。</div>' +
    '<div class="res-row sub">可在「' + esc(secName(sec)) + '资费」列表确认当前在售业务。</div>');
}

/* ===== 公告列表 ===== */
function renderAnnounce() {
  const box = $("announceBox");
  const sub = $("announceSub");
  loadAnnounce().then((d) => {
    if (!d || !d.items || !d.items.length) {
      if (sub) sub.textContent = "";
      box.innerHTML = '<div class="empty">暂无公告数据</div>';
      return;
    }
    if (sub) sub.innerHTML = "数据更新时间：" + esc(d.updated || "");
    box.innerHTML = d.items.map((it, i) => {
      const att = (it.attachments && it.attachments.length)
        ? '<div class="ann-att">' + it.attachments.map((a) =>
            '<a class="ann-att-btn" href="' + esc(a.url) + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">附件 · ' + esc(a.name || "下载") + "</a>").join("") + "</div>"
        : "";
      const body = (it.content && it.content.trim())
        ? '<div class="ann-content">' + it.content + "</div>"
        : '<div class="ann-noimg">该公告正文以图片形式发布，请点击查看官网原文。</div>';
      return '<div class="ann-item" data-i="' + i + '">' +
        '<div class="ann-head">' +
        '<span class="ann-date">' + esc(it.date || "") + "</span>" +
        '<span class="ann-title">' + esc(it.title || "") + "</span>" +
        '<span class="ann-arrow"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>' +
        "</div>" +
        (it.summary ? '<div class="ann-summary">' + esc(it.summary) + "</div>" : "") +
        '<div class="ann-body">' + body + att +
        '<div class="ann-more"><a href="' + esc(it.page_url || "#") + '" target="_blank" rel="noopener">查看官网原文</a></div>' +
        "</div></div>";
    }).join("");
    box.querySelectorAll(".ann-item").forEach((el) => {
      const h = el.querySelector(".ann-head");
      h.addEventListener("click", () => {
        const open = el.classList.toggle("open");
        const arw = el.querySelector(".ann-arrow");
        if (arw) arw.style.transform = open ? "rotate(180deg)" : "";
      });
    });
  }).catch(() => {
    if (sub) sub.textContent = "";
    box.innerHTML = '<div class="empty">公告数据加载失败，请稍后重试</div>';
  });
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

/* 启动：支持 hash 直达（如 #history 直达变化历史），默认总览 */
(function boot() {
  const raw = (location.hash || "").replace("#", "").trim();
  const valid = ["overview", "quanguo", "prov", "history", "announce", "about"].indexOf(raw) >= 0;
  goTab(valid ? raw : "overview");
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
    ".notice-top{background:linear-gradient(120deg,#0d8bec,#33a6ff);color:#fff;padding:18px 20px 14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
    ".notice-ico{width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center;font-size:17px;flex:none}",
    ".notice-top h3{margin:0;font-size:16px;font-weight:600;flex:1;min-width:120px}",
    ".notice-top .notice-tag{font-size:11px;color:#fff;background:rgba(255,255,255,.25);border:1px solid rgba(255,255,255,.5);border-radius:10px;padding:2px 8px;font-weight:400}",
    ".notice-body{padding:16px 20px 6px}",
    ".notice-body p{margin:0 0 10px;color:#555}",
    ".notice-list{margin:0;padding:0;list-style:none}",
    ".notice-list li{position:relative;padding:4px 0 4px 22px;margin:0}",
    ".notice-list li:before{content:'✓';position:absolute;left:0;top:4px;color:#17a34a;font-weight:700}",
    ".notice-ft{padding:12px 20px 18px;text-align:right}",
    ".notice-ok{border:0;background:linear-gradient(120deg,#0d8bec,#33a6ff);color:#fff;font-size:14px;padding:9px 26px;border-radius:20px;cursor:pointer;font-weight:500;box-shadow:0 4px 12px rgba(0,0,0,.14)}",
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

/* ---------- 检测资费（刷新按钮） ---------- */
const RK = "trf_last_check";
const btnRefresh = $("refreshBtn");

function fetchNoCache(file) {
  return fetchTimeout(DATA + file, { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((j) => { delete cache[file]; return j; });
}

function openModal(title, html) {
  $("modalTitle").textContent = title;
  $("modalBody").innerHTML = html;
  $("modalMask").classList.add("show");
}
function closeModal() { $("modalMask").classList.remove("show"); $("modalMask").classList.remove("warn"); }

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
        openModal("检测完成",
          '<div class="res-row">已建立首次检测基线。</div>' +
          '<div class="res-row sub">数据快照时间：' + esc(updated || "未知") + "</div>" +
          '<div class="res-row sub">历史变更记录：' + hlen + " 条</div>");
      } else if (hlen > (prev.hlen || 0)) {
        const newHist = Array.isArray(hist) ? hist.slice(prev.hlen || 0) : [];
        const detail = describeHistory(newHist) ||
          '<div class="res-row">检测到资费变化，可到「变化历史」页查看详情。</div>';
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("检测到资费变化", detail + '<div class="res-row sub">快照时间：' + esc(updated || "未知") + "</div>");
      } else if (updated && prev.updated !== updated) {
        localStorage.setItem(RK, JSON.stringify(snap));
        openModal("数据快照已更新",
          '<div class="res-row">资费数据快照已更新，新增/下架条数为 0，可能为字段级微调。</div>' +
          '<div class="res-row sub">快照时间：' + esc(updated) + "</div>");
      } else {
        openModal("无变化",
          '<div class="res-row ok">暂未检测到资费变化。</div>' +
          '<div class="res-row sub">数据快照时间：' + esc(updated || "未知") + "</div>");
      }
      if ($("updateTime")) $("updateTime").textContent = "更新于 " + (updated || "未知");
    })
    .catch((e) => {
      openModal("检测失败", '<div class="res-row">数据获取失败：' + esc(e.message) + "</div>");
    })
    .finally(() => {
      checking = false;
      btnRefresh.classList.remove("busy");
      btnRefresh.textContent = oldText;
    });
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
