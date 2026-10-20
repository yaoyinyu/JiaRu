const $ = (selector) => document.querySelector(selector);
const esc = (value = "") => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const storageKey = "jiaru-consumer-design-v1";
const looks = [
  { id: 1, name: "把温柔留在指尖", original: "渐变裸粉", tag: "自然", scene: "日常", colors: ["#d4a396", "#e8c6b7", "#b9857b"], description: "柔和裸粉与细腻渐层，在不经意的抬手之间，留下一点温柔。" },
  { id: 2, name: "日常，也值得精致", original: "法式白边", tag: "简约", scene: "通勤", colors: ["#dfc3b2", "#fff9ef", "#b49a88"], description: "干净的白色甲尖与轻盈底色。简单、耐看，也适合与你的日常衣橱相处。" },
  { id: 3, name: "一点恰好的微光", original: "亮片闪粉", tag: "轻闪", scene: "约会", colors: ["#c6b6a6", "#c59c8d", "#dfd4c5"], description: "把光藏在细节里。低调的闪粉，让每一个小动作都变得生动。" },
  { id: 4, name: "一抹纯粹的喜欢", original: "简约纯色", tag: "简约", scene: "日常", colors: ["#af6a65", "#d09c8b", "#e5c4af"], description: "不复杂的颜色，不费力的好看。选一抹喜欢的纯色，为今天留个好心情。" },
  { id: 5, name: "旧时光的新心动", original: "复古花纹", tag: "复古", scene: "出游", colors: ["#823f3c", "#b98b66", "#d5c3a8"], description: "暖调花纹与复古细节，像一件愿意反复穿着的衣服，有自己的韵味。" },
  { id: 6, name: "给特别日子的小礼物", original: "宝石镶嵌", tag: "装饰", scene: "聚会", colors: ["#ad8770", "#dad0b7", "#a9aa98"], description: "精巧的装饰与丰富层次，为值得纪念的日子，添一点仪式感。" },
];
let persisted = {};
let storageAvailable = true;
try { persisted = JSON.parse(localStorage.getItem(storageKey) ?? "{}"); } catch { storageAvailable = false; }
if (!persisted || typeof persisted !== "object" || Array.isArray(persisted)) persisted = {};
const numericList = (value) => Array.isArray(value) ? value.filter((id) => looks.some((look) => look.id === id)) : [];
const textList = (value) => Array.isArray(value) ? value.filter((v) => typeof v === "string").slice(0, 10) : [];
const state = {
  saved: numericList(persisted.saved), liked: numericList(persisted.liked), following: persisted.following === true,
  profile: typeof persisted.profile === "string" ? persisted.profile.slice(0, 600) : "",
  styles: textList(persisted.styles), scenes: textList(persisted.scenes), length: ["短甲", "中长甲", "长甲"].includes(persisted.length) ? persisted.length : "短甲",
  learned: persisted.learned === true, onboarded: persisted.onboarded === true,
  loggedIn: false, filter: "全部", query: "", otherPerson: false,
  selectedLook: 1, generationByMode: { photo: "idle", create: "idle" }, resultLooks: { photo: 1, create: 1 },
  createDraft: "", photoDraft: "", preferenceNote: "", publishDraft: "", publishTitle: "", posts: [],
  profileDraft: typeof persisted.profile === "string" ? persisted.profile.slice(0, 600) : "",
  profileLearnDraft: persisted.learned === true, onboardingSummaryDraft: null, onboardingLearnDraft: persisted.learned === true,
  publishSource: "本人拍摄或创作", publishRights: false, schemeOrigin: "photo",
  uploads: { own: null, other: null, reference: null, publish: null },
};
let currentRoute = "home";
const jobTimers = {};
let toastTimer;
let focusAfterRoute = true;
let renderedHash = "";
let pendingNavigation;
let routeAnimation;
let revealObserver;
let modalTrigger;
let searchComposing = false;
let composingField;
let deferredRender = false;
const schemeFiles = new Map();
const exportUrls = new Set();
const uploadSequence = {};
const scrollPositions = new Map();
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const finePointer = matchMedia("(hover: hover) and (pointer: fine)");
document.body.dataset.input = finePointer.matches ? "mouse" : "touch";
if ("scrollRestoration" in history) history.scrollRestoration = "manual";
const icons = {
  home: '<path d="M3 10.5 12 3l9 7.5M5 9v11h14V9M9 20v-7h6v7"/>',
  hand: '<path d="M7 12V6a1.5 1.5 0 0 1 3 0v5-7a1.5 1.5 0 0 1 3 0v7-6a1.5 1.5 0 0 1 3 0v7-4a1.5 1.5 0 0 1 3 0v7c0 4-2 6-6 6h-1c-3 0-4-1-6-4l-3-4c-1-2 1-3 2-2l2 2Z"/>',
  sparkle: '<path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z"/><path d="m20 3 .5 1.5L22 5l-1.5.5L20 7l-.5-1.5L18 5l1.5-.5L20 3Z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  bookmark: '<path d="M6 3h12v18l-6-4-6 4V3Z"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  back: '<path d="M20 12H5m6-6-6 6 6 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  camera: '<path d="M8 5 6 8H3v12h18V8h-3l-2-3H8Z"/><circle cx="12" cy="13" r="4"/>',
  photo: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
  heart: '<path d="M20.5 5.5c-3-3-6-1-8.5 1-2.5-2-5.5-4-8.5-1S2 12 12 21c10-9 11.5-12.5 8.5-15.5Z"/>',
  check: '<path d="m5 12 4 4L20 5"/>',
  settings: '<path d="m10 3-.8 2.2-2 .8L5 5l-2 3 1.7 1.7-.2 2.3L3 14l2 3 2.3-.3 1.7 1.5L10 21h4l1-2.8 1.7-1.5 2.3.3 2-3-1.5-2 .2-2.3L21 8l-2-3-2.2 1-2-.8L14 3h-4Z"/><circle cx="12" cy="12" r="3"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  share: '<path d="M12 16V3m-4 4 4-4 4 4M6 10H3v11h18V10h-3"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] ?? icons.sparkle}</svg>`;
const photo = (id) => `/assets/ai-look-${id}.jpg`;
const byId = (id) => looks.find((look) => look.id === Number(id)) ?? looks[0];
const action = (name, label, className = "secondary", extra = "") => `<button type="button" class="${className}" data-action="${name}" ${extra}>${label}</button>`;
const link = (hash, label, className = "text-button", attributes = "") => `<a href="#${hash}" class="${className}" ${attributes}>${label}</a>`;
const intro = (english, title, description) => `<header class="page-intro"><p class="eyebrow coral">${english}</p><h1>${title}</h1><p>${description}</p></header>`;
const note = (text) => `<details class="capability-note"><summary>${icon("info")}<span>使用说明</span></summary><p>${text}</p></details>`;

function focusIdentity(element = document.activeElement) {
  if (!element || element === document.body) return null;
  if (element.matches?.("button[type=submit]") && element.closest("form")?.id) return `#${CSS.escape(element.closest("form").id)} button[type=submit]`;
  if (element.dataset?.upload) return `input[data-upload="${element.dataset.upload}"]`;
  if (element.id) return `#${CSS.escape(element.id)}`;
  if (element.matches?.("[data-action]")) return `[data-action="${element.dataset.action}"]${element.dataset.id ? `[data-id="${element.dataset.id}"]` : ""}${element.dataset.filter ? `[data-filter="${element.dataset.filter}"]` : ""}`;
  if (element.matches?.("a[href]")) return `a[href="${CSS.escape(element.getAttribute("href"))}"]`;
  return null;
}
function motion(element, frames, options) {
  if (reducedMotion.matches || !element?.animate) return null;
  return element.animate(frames, { duration: 240, easing: "cubic-bezier(.22,.68,.2,1)", ...options });
}
function revealCards() {
  revealObserver?.disconnect();
  if (reducedMotion.matches || typeof IntersectionObserver !== "function") return;
  revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(({ isIntersecting, target }) => {
      if (!isIntersecting) return;
      target.classList.add("is-visible");
      motion(target, [{ opacity: .35, transform: "translateY(10px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 380 });
      revealObserver.unobserve(target);
    });
  }, { threshold: .08 });
  document.querySelectorAll(".look-card").forEach((card) => { card.classList.add("reveal"); revealObserver.observe(card); });
}

function persist() {
  const data = Object.fromEntries(["saved", "liked", "following", "profile", "styles", "scenes", "length", "learned", "onboarded"].map((key) => [key, state[key]]));
  try { localStorage.setItem(storageKey, JSON.stringify(data)); }
  catch { storageAvailable = false; toast("浏览器未能保存预览数据，本次会话仍可继续；请勿将它视为已持久保存。"); }
}
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4400);
}
function modal(title, body) {
  const dialog = $("#sheet");
  modalTrigger = focusIdentity();
  dialog.innerHTML = `<div class="dialog-header"><h2 id="sheet-title">${esc(title)}</h2>${action("close-modal", icon("close"), "round-button", 'aria-label="关闭"')}</div><div class="dialog-body">${body}</div>`;
  dialog.setAttribute("aria-labelledby", "sheet-title");
  if (!dialog.open) { dialog.showModal(); document.body.classList.add("sheet-open"); }
}
function navigate(hash, { restore = false } = {}) {
  scrollPositions.set(renderedHash, window.scrollY);
  if (hash.startsWith("scheme/")) state.schemeOrigin = currentRoute === "create" ? "create" : "photo";
  pendingNavigation = { restore };
  if (location.hash === `#${hash}`) {
    pendingNavigation = undefined;
    window.scrollTo({ top: restore ? scrollPositions.get(hash) ?? 0 : 0, behavior: reducedMotion.matches ? "auto" : "smooth" });
  } else location.hash = hash;
}
function preferenceText() {
  const style = state.styles.length ? state.styles.join("、") : "尚待探索的风格";
  const scene = state.scenes.length ? state.scenes.join("、") : "日常";
  return `偏爱${style}，主要用于${scene}，喜欢${state.length}。${state.preferenceNote.trim() ? `补充：${state.preferenceNote.trim().slice(0, 100)}` : "愿意尝试有细节、不过分张扬的设计。"}`;
}
function nav() {
  const section = ["tryon", "photo", "camera", "scheme"].includes(currentRoute) ? "tryon" : currentRoute === "create" ? "create" : ["me", "saved", "profile", "publish"].includes(currentRoute) ? "me" : "home";
  const tabs = [["home", "为你", "home"], ["tryon", "试戴", "hand"], ["create", "创作", "sparkle"], ["me", "我的", "user"]];
  const navLinks = (bottom) => tabs.map(([id, text, symbol]) => `<a href="#${id}" ${section === id ? 'aria-current="page"' : ""}>${bottom ? icon(symbol) : ""}<span>${text}</span></a>`).join("");
  return { top: navLinks(false), bottom: navLinks(true) };
}
function shell(content) {
  const navigation = nav();
  $("#app").innerHTML = `<header class="site-header"><a class="brand" href="#home" aria-label="甲如，为你"><span class="wordmark">JiaRu<span class="brand-sub">nail atelier</span></span><span class="brand-cn">甲如</span></a><nav class="desktop-links" aria-label="主导航">${navigation.top}</nav><div class="header-actions">${link("profile", icon("settings"), "round-button", 'aria-label="我的偏好"')}${link("saved", icon("bookmark"), "round-button", 'aria-label="我的收藏"')}</div></header><main id="main" tabindex="-1"><div class="page-view">${content}${!storageAvailable ? note("本地存储不可用，当前内容仅保留在本次会话。") : ""}</div><footer class="footer-note"><span>JiaRu · 指尖的日常美学</span>${action("show-notes", `${icon("info")} 关于预览`, "icon-action", 'aria-label="能力与数据边界"')}</footer><details class="scenario-toolbar"><summary>${icon("settings")} 预览设置</summary><div class="scenario-actions">${action("show-error", "失败状态", "text-button")}${action("empty", "空内容", "text-button")}${action("wireframe", "线框视图", "text-button")}${action("reset", "重置本地预览", "text-button")}</div></details></main><nav class="bottom-nav" aria-label="主导航">${navigation.bottom}</nav>`;
}
function lookCard(look) {
  const saved = state.saved.includes(look.id);
  return `<article class="look-card"><div class="look-cover"><a href="#look/${look.id}" aria-label="查看${look.name}"><img src="${photo(look.id)}" alt="${look.original}，AI 演示款式" loading="lazy" width="500" height="625"></a><span class="image-label">AI 灵感</span>${action("save", icon("bookmark"), `save-button${saved ? " is-saved" : ""}`, `data-id="${look.id}" aria-label="${saved ? "取消收藏" : "收藏"}${look.name}" aria-pressed="${saved}"`)}</div><div class="card-title-row"><h3>${link(`look/${look.id}`, look.name, "")}</h3><span class="color-dots" aria-hidden="true">${look.colors.map((color) => `<i style="background:${color}"></i>`).join("")}</span></div><p class="card-caption">${look.tag} · ${look.scene}</p></article>`;
}
function home() {
  const hero = `<section class="hero"><div class="hero-copy"><p class="eyebrow coral season-label">THE EVERYDAY MUSE</p><h1>把喜欢的自己，<br>留在<em>每一次抬手。</em></h1><p class="hero-desc">让喜欢，轻轻落在指尖。</p>${link("tryon", `试戴这一款 ${icon("arrow")}`, "primary")}</div><div class="hero-art" aria-label="本期纤细手背与五种精致美甲灵感"><img class="main-photo" src="/assets/hero-hand-diversity-v3.png" alt="纤细白皙的手背，五指分别展示短圆冰透、长梯形猫眼、椭圆贝母、尖杏仁碎钻与短方圆几何美甲，AI 拼贴主视觉" width="1122" height="1402" fetchpriority="high"><span class="art-number">JIARU EDIT / 01 · AI 灵感</span><i class="art-dot"></i><span class="art-caption">A little more you.</span></div></section>`;
  return `${hero}<aside class="onboarding-callout"><span class="callout-mark">${icon("sparkle")}</span><div class="callout-copy"><h2>找到你的风格</h2><p>${state.profile ? esc(state.profile.slice(0, 35)) : "从几个喜欢的词开始。"}</p></div>${link("onboarding/1", `${icon("arrow")}`, "text-button", 'aria-label="了解或调整我的偏好"')}</aside><div class="section-heading"><div><p class="eyebrow muted">CURATED FOR YOU</p><h2>此刻心动</h2></div>${link("saved", icon("bookmark"), "round-button", 'aria-label="查看我的收藏"')}</div><div class="search-box">${icon("search")}<input type="search" id="look-search" placeholder="法式、裸粉、通勤…" aria-label="搜索款式" value="${esc(state.query)}"></div><div class="filters" role="group" aria-label="款式分类">${["全部", "自然", "简约", "轻闪", "复古", "通勤"].map((tag) => action("filter", tag, "chip", `data-filter="${tag}" aria-pressed="${state.filter === tag}"`)).join("")}</div><div id="look-results" aria-live="polite">${lookResults()}</div>`;
}
function lookResults() {
  const filtered = looks.filter((look) => (state.filter === "全部" || look.tag === state.filter || look.scene === state.filter) && `${look.name}${look.original}${look.tag}${look.scene}`.includes(state.query.trim()));
  return filtered.length ? `<div class="look-grid">${filtered.map(lookCard).join("")}</div>` : empty("还没有找到这份心动", "换个词，或创造一点新灵感。", link("create", "去创作", "primary"));
}
function empty(title, description, buttons = "") { return `<section class="empty-state">${icon("sparkle")}<h2>${title}</h2><p>${description}</p>${buttons}</section>`; }
function tryon() {
  return `${intro("A LOOK ON YOU", "指尖，换一种心情", "选一种方式，开始试戴。")}<label class="switch-row"><input type="checkbox" id="other-person" ${state.otherPerson ? "checked" : ""}>为身边的人试戴</label>${state.otherPerson ? note("沿用你的审美，只更换本次照片，不覆盖本人档案。") : ""}<div class="choice-grid"><a href="#photo" class="mode-card" aria-label="用一张照片"><span class="mode-illustration">${icon("photo")}</span><h2>照片试戴</h2><p>AI 上手参考</p><span class="text-button" aria-hidden="true">${icon("arrow")}</span></a><a href="#camera" class="mode-card" aria-label="打开摄像头"><span class="mode-illustration">${icon("camera")}</span><h2>摄像头试戴</h2><p>实时 AR · 流程预览</p><span class="text-button" aria-hidden="true">${icon("arrow")}</span></a></div>${note("设计预览不会上传照片或启动摄像头，真实 AI 与 AR 尚未接入。")}`;
}
function uploadBox(slot, label) {
  const uploaded = state.uploads[slot];
  return `<label class="upload-box">${uploaded ? `<img src="${uploaded.url}" alt="${label}，仅本次本地预览">${esc(uploaded.name)}` : `${icon("upload")}<span>${label}</span><small>JPG / PNG / WebP · 最多 10 MB</small>`}<input type="file" accept="image/jpeg,image/png,image/webp" data-upload="${slot}" aria-label="${label}"></label>`;
}
function resultPanel(mode) {
  if (state.generationByMode[mode] === "loading") return empty("让灵感慢慢浮现", "正在演示等待状态，不会调用 AI 或产生费用。", '<div class="loading-orbit" aria-label="加载中"></div>');
  if (state.generationByMode[mode] === "error") return `<section class="empty-state"><h2>这次没有完成</h2><p>失败状态演示。你的描述、选款与本地照片仍在，可以重试。</p>${action("generate", "保留输入，重新尝试", "primary", `data-mode="${mode}"`)}</section>`;
  if (state.generationByMode[mode] === "ready") return `<section class="sample-result"><div class="result-image"><img src="${photo(state.resultLooks[mode])}" alt="结果布局示例，既有 AI 图库素材，并非本次生成"></div><span class="image-label">结果布局示例 · 非本次生成</span>${note("这里展示既有样图以便评审布局，尚未根据你的照片或描述生成。")}<div class="action-row">${link(`scheme/${state.resultLooks[mode]}`, "整理成美甲方案", "primary")}${action("save", "收藏示例款", "secondary", `data-id="${state.resultLooks[mode]}"`)}</div></section>`;
  return empty("你的新灵感，会出现在这里", "先选一款喜欢的设计，或写下你脑海中的颜色与感觉。", "");
}
function photoTryon() {
  const slot = state.otherPerson ? "other" : "own";
  const look = byId(state.selectedLook);
  return `${link("tryon", `${icon("back")} 选择其他试戴方式`, "back-link")}${intro("PHOTO TRY-ON", "在你的手上，想象新风格", "AI 上手参考 · 帮你找到搭配灵感。")}<div class="split"><section class="panel"><h2>${state.otherPerson ? "对方这次的手部照片" : "你的手部照片"}</h2>${uploadBox(slot, "选择一张手背清晰、光线均匀的照片")}<p class="inline-note">照片仅留在本次浏览器内存；刷新后需重新选择。</p><div class="field"><label for="selected-look">这次想试的款</label><select id="selected-look">${looks.map((item) => `<option value="${item.id}" ${item.id === look.id ? "selected" : ""}>${item.original} · ${item.name}</option>`).join("")}</select></div><div class="field"><label for="photo-prompt">还想调整什么？</label><textarea id="photo-prompt" data-draft="photoDraft" maxlength="300" placeholder="比如：保留法式白边，底色更偏奶茶一些…">${esc(state.photoDraft)}</textarea></div>${note("正式版将向选定 AI 服务发送照片与描述；具体服务、费用与处理条款待确认。当前预览不上传。")}<div class="action-row">${action("generate", state.uploads[slot] ? "预览上手结果布局" : "先添加手部照片", "primary", `data-mode="photo" ${state.generationByMode.photo === "loading" ? "disabled" : ""}`)}</div><p class="inline-note">此按钮只演示交互状态，不执行生成。</p></section><div>${resultPanel("photo")}</div></div>`;
}
function camera() {
  return `${link("tryon", `${icon("back")} 选择其他试戴方式`, "back-link")}${intro("LIVE TRY-ON", "换个颜色，看看此刻的你", "实时摄像头体验将在独立验收后接入。此提案不启动摄像头，也不加载模型。")}<div class="split"><section>${empty("把手轻轻放进画面", "靠近自然光，让手背与五指清晰可见。", action("camera-info", `${icon("camera")} 查看摄像头开启流程`, "primary"))}</section><section class="panel"><h2>先选一种心情</h2><div class="tag-options">${looks.slice(0, 4).map((look) => action("camera-color", look.original, "chip", `data-id="${look.id}"`)).join("")}</div>${note("需覆盖：权限询问、用户拒绝、未找到设备、模型加载、未检测到手和重新尝试。当前只呈现流程，未证明 AR 贴合质量。")}${link("photo", "也可以用照片开始", "secondary")}</section></div>`;
}
function create() {
  return `${intro("YOUR NAIL ATELIER", "让灵感，成为一款美甲", "说说喜欢的颜色与质感。")}<div class="split"><section class="panel"><p class="eyebrow coral">START WITH A FEELING</p><h2>今天，想要怎样的美？</h2><div class="tag-options">${["奶油裸色", "极简法式", "低调微闪", "复古暖调"].map((word) => action("prompt", word, "chip", `data-prompt="${word}"`)).join("")}</div><div class="field"><label for="create-prompt">描述你的灵感</label><textarea id="create-prompt" maxlength="300" data-draft="createDraft" placeholder="比如：适合通勤的奶茶色短甲，加一点细细的金色线条…">${esc(state.createDraft)}</textarea></div><div class="field"><label>参考图，可选</label>${uploadBox("reference", "添加喜欢的款式或手部照片")}</div>${action("advanced", "画面比例与生成设置", "text-button")}${note("正式生成会发送文字及你主动选择的参考图。当前不连接任何服务，也不产生费用。")}<div class="action-row">${action("generate", `${icon("sparkle")} 预览创作结果布局`, "primary", `data-mode="create" ${state.generationByMode.create === "loading" ? "disabled" : ""}`)}</div></section><div>${resultPanel("create")}</div></div>`;
}
function detail(id) {
  const look = byId(id);
  state.selectedLook = look.id;
  return `${link("home", `${icon("back")} 回到灵感`, "back-link")}<div class="split"><div class="detail-image"><img src="${photo(look.id)}" alt="${look.original}，AI 生成演示素材"><span class="image-label">AI 设计参考 · 非真实商品</span></div><section><p class="eyebrow coral">THE JIARU EDIT / ${String(look.id).padStart(2, "0")}</p><h1 class="detail-title">${look.name}</h1><p class="detail-summary">${look.description}</p><div class="tag-options" style="margin-top:20px"><span class="chip">${look.tag}</span><span class="chip">${look.scene}</span><span class="chip">${look.original}</span></div><div class="author-row"><a class="avatar" href="#creator" aria-label="查看甲如灵感编辑部主页">J</a><a href="#creator"><strong>甲如灵感编辑部</strong><p>演示账号 · 编辑精选</p></a>${action("follow", state.following ? "已关注" : "+ 关注", "secondary", `aria-pressed="${state.following}"`)}</div><p class="inline-note">推荐理由示例：款式标签与你选择的风格相近。真实个性化推荐尚未接入。</p><div class="action-row">${link("tryon", `试戴这一款 ${icon("arrow")}`, "primary")}</div><div class="action-row">${action("save", `${icon("bookmark")} ${state.saved.includes(look.id) ? "已收藏" : "收藏灵感"}`, "secondary", `data-id="${look.id}" aria-pressed="${state.saved.includes(look.id)}"`)}${action("like", `${icon("heart")} ${state.liked.includes(look.id) ? "已喜欢" : "喜欢"}`, "secondary", `data-id="${look.id}" aria-pressed="${state.liked.includes(look.id)}"`)}</div>${link(`scheme/${look.id}`, `整理成方案，给美甲师看看 ${icon("arrow")}`)}${note("点赞、收藏、关注仅保存在独立预览空间；不会影响旧版账号或真实推荐。")}</section></div>`;
}
function saved() {
  const selected = looks.filter((look) => state.saved.includes(look.id));
  return `${intro("YOUR LITTLE COLLECTION", "喜欢，慢慢收藏", "留住这一刻的心动。")}${selected.length ? `<div class="look-grid">${selected.map(lookCard).join("")}</div>` : empty("第一份心动，还在等你", "遇到喜欢的款式，点一下收藏。下一次就能在这里找到。", link("home", "去发现喜欢", "primary"))}`;
}
function profile() {
  return `${intro("A STYLE THAT GROWS WITH YOU", "你的偏好，由你定义", "喜欢与不喜欢，都由你决定。")}<div class="split"><section><div class="preference-card"><p class="eyebrow">MY STYLE NOTES · 偏好描述</p><blockquote>${esc(state.profile || "还没有写下你的偏好。几个关键词，就能开始认识自己喜欢什么。")}</blockquote>${link("onboarding/1", "重新选择偏好", "text-button")}</div><form id="profile-form"><div class="field"><label for="profile-text">直接修改你的描述</label><textarea id="profile-text" data-draft="profileDraft" maxlength="600" placeholder="说说自己喜欢与不喜欢的设计…">${esc(state.profileDraft)}</textarea></div><label class="switch-row"><input type="checkbox" id="learn-toggle" ${state.profileLearnDraft ? "checked" : ""}>允许用后续收藏完善偏好（未来功能，此处只记录选择）</label><button class="primary full-width" type="submit">保存到本地预览</button></form></section><aside class="panel"><h2>让推荐理解你，也听你的</h2><p>收藏与标签是主要线索，手部特点只是较轻的参考。为他人试戴只更换本次照片。</p>${note("此原型的描述来自选项模板，不是语言模型分析。收藏不会在后台悄悄触发任何模型调用。")}${action("cloud-info", "查看跨设备保存方案", "secondary")}</aside></div>`;
}
function me() {
  return `<div class="profile-head"><span class="avatar">J</span><div><h1>${state.loggedIn ? "我的指尖日记" : "你的美甲日记"}</h1><p>${state.loggedIn ? "模拟登录态 · 仅用于评审布局" : "收藏、灵感，还有一点喜欢。"}</p></div></div><div class="stats"><div><strong>${state.posts.length}</strong>本地发布预览</div><div><strong>${state.saved.length}</strong>收藏灵感</div><div><strong>${state.following ? 1 : 0}</strong>预览关注</div></div><div class="split"><section><div class="preference-card"><p class="eyebrow">MY STYLE NOTES</p><blockquote>${esc(state.profile || "审美没有标准答案，喜欢就是很好的开始。")}</blockquote>${link("profile", `我的偏好描述 ${icon("arrow")}`)}</div>${link("saved", `${icon("bookmark")} 我的收藏 ${icon("arrow")}`, "list-row")}${link("publish", `${icon("upload")} 发布一份新灵感 ${icon("arrow")}`, "list-row")}${link("creator/me", `${icon("user")} 我的公开主页 ${icon("arrow")}`, "list-row")}${action("cloud-info", `${icon("lock")} 本地照片与跨设备保存 ${icon("arrow")}`, "list-row")}${action("login", `${icon("user")} ${state.loggedIn ? "查看模拟账号说明" : "登录后的空间，先体验看看"} ${icon("arrow")}`, "list-row")}</section><aside class="panel"><h2>一些属于自己的空间</h2><p>收藏、灵感、创作与方案，慢慢汇成你的美甲日记。登录后的云端同步将单独建设。</p>${note("原照片默认本地，特点关键词同步云端是已确认的正式版方向。此预览两者都不会上传。")}${link("tryon", "为身边的人试一款", "secondary")}</aside></div>`;
}
function creator(mine) {
  return `${link(mine ? "me" : `look/${state.selectedLook}`, `${icon("back")} 返回`, "back-link")}<div class="profile-head"><span class="avatar">J</span><div><h1>${mine ? "我的灵感小馆" : "甲如灵感编辑部"}</h1><p>${mine ? "公开主页布局预览，尚未实际公开" : "演示账号 · 收集日常里细小而确定的美"}</p></div></div>${mine ? note("这里只呈现你在本次会话提交的发布预览。刷新后不保留上传照片，没有真实公开地址。") : action("follow", state.following ? "已关注" : "+ 关注", "secondary", `aria-pressed="${state.following}"`)}<div class="section-heading"><div><p class="eyebrow muted">STYLE JOURNAL</p><h2>${mine ? "发布的灵感" : "编辑精选"}</h2></div></div>${mine ? state.posts.length ? `<div class="look-grid">${state.posts.map((post) => `<article class="look-card"><div class="look-cover"><img src="${post.url}" alt="本地发布预览：${esc(post.title)}"><span class="image-label">仅本地 · 未公开</span></div><h3 class="card-title-row">${esc(post.title)}</h3><p class="card-caption">${esc(post.description)}</p></article>`).join("")}</div>` : empty("让第一份灵感，从这里开始", "分享你的美甲审美与喜欢的款式。正式公开发布与审核尚未接入。", link("publish", "预览发布流程", "primary")) : `<div class="look-grid">${looks.slice(0, 3).map(lookCard).join("")}</div>`}`;
}
function publish() {
  return `${intro("SHARE A LITTLE BEAUTY", "分享一点美", "整理作品 · 仅本地预览")}<div class="split"><form id="publish-form" class="panel">${uploadBox("publish", "上传你想分享的美甲款式")}<div class="field"><label for="publish-title">给这份灵感起个名字</label><input id="publish-title" type="text" maxlength="40" required data-draft="publishTitle" value="${esc(state.publishTitle)}" placeholder="比如：我的秋日奶茶法式"></div><div class="field"><label for="publish-text">风格、场景与创作说明</label><textarea id="publish-text" maxlength="300" data-draft="publishDraft" placeholder="说说它让你心动的地方…">${esc(state.publishDraft)}</textarea></div><div class="field"><label for="publish-source">图片来源</label><select id="publish-source">${["本人拍摄或创作", "已获授权转载", "AI 生成设计"].map((source) => `<option ${source === state.publishSource ? "selected" : ""}>${source}</option>`).join("")}</select></div><label class="switch-row"><input type="checkbox" id="publish-rights" ${state.publishRights ? "checked" : ""} required>我有权分享这张图片，并愿意在正式发布时公开。</label><button class="primary full-width" type="submit">${state.loggedIn ? "生成本地发布预览" : "体验登录后，再预览发布"}</button></form><aside class="panel"><h2>分享风格，也尊重创作</h2><p>记录来源，区分实拍与 AI 设计。个人主页、点赞、收藏与关注先行；评论和私信后续再加入。</p>${note("此原型不会把照片上传或公开；公开内容后端、审核机制和真实账号关联均待实施。")}</aside></div>`;
}
function scheme(id) {
  const look = byId(id);
  return `${intro("YOUR NAIL NOTE", "把喜欢，带给美甲师", "一张卡，装下款式与想法。")}<div class="split"><article class="scheme-card" id="scheme-card"><div class="scheme-top"><span class="wordmark">JiaRu</span><span class="eyebrow muted">MY NAIL NOTE</span></div><div class="scheme-photo"><img src="${photo(look.id)}" alt="${look.original}的款式参考，AI 演示素材"></div><h2>${look.name}</h2><p>${look.description}</p><dl><dt>风格参考</dt><dd>${look.original} / ${look.tag}</dd><dt>长度偏好</dt><dd>${esc(state.length)}</dd><dt>使用场景</dt><dd>${esc(state.scenes.join("、") || look.scene)}</dd><dt>补充需求</dt><dd>${esc((state.schemeOrigin === "create" ? state.createDraft : state.photoDraft) || "结合实际甲面与美甲师建议调整。")}</dd></dl><div class="signature">AI 灵感参考 · 非实际制作效果 · JIARU</div></article><aside class="panel"><h2>一份灵感，一次更好的沟通</h2><p>当前卡片使用已选的演示款式，并不包含你手部照片的生成结果。正式制作前，请与美甲师确认材料、长度与可实现效果。</p><div class="action-row">${action("share-scheme", `${icon("share")} 分享方案`, "primary", `data-id="${look.id}" disabled aria-busy="true"`)}</div><div class="action-row">${action("download-scheme", `${icon("photo")} 保存图片`, "secondary", `data-id="${look.id}"`)}</div><div class="action-row">${action("copy-scheme", "复制方案文字", "secondary", `data-id="${look.id}"`)}</div>${link(state.schemeOrigin, `${icon("back")} 返回继续调整`, "text-button", "data-return-editor")}</aside></div>`;
}
function tagOption(value, group, checked, radio = false) {
  return `<label class="tag-option"><input type="${radio ? "radio" : "checkbox"}" name="${group}" value="${value}" ${checked ? "checked" : ""}><span>${value}</span></label>`;
}
function onboarding(step) {
  const stage = Math.max(1, Math.min(4, Number(step) || 1));
  let content;
  if (stage === 1) content = `<p class="step-number">01.</p><h1 class="step-title">哪些感觉，让你心动？</h1><p class="step-description">不用急着给风格下定义。先选几个喜欢的词，也可以不选。</p><fieldset class="tag-options"><legend class="skip-link">喜欢的风格，可多选</legend>${["自然", "简约", "轻闪", "复古", "温柔", "个性"].map((word) => tagOption(word, "styles", state.styles.includes(word))).join("")}</fieldset><div class="field"><label for="onboarding-note">用自己的话补充一点</label><textarea id="onboarding-note" data-draft="preferenceNote" maxlength="300" placeholder="比如：低饱和、不夸张，但希望有一点细节…">${esc(state.preferenceNote)}</textarea></div>`;
  if (stage === 2) content = `<p class="step-number">02.</p><h1 class="step-title">美，也要适合你的日常。</h1><p class="step-description">长期喜好与这次需求可以不同，以后都能调整。</p><fieldset class="field"><legend>主要使用场景，可多选</legend><div class="tag-options">${["日常", "通勤", "约会", "出游", "聚会", "婚礼"].map((word) => tagOption(word, "scenes", state.scenes.includes(word))).join("")}</div></fieldset><fieldset class="field"><legend>平时更舒服的长度</legend><div class="tag-options">${["短甲", "中长甲", "长甲"].map((word) => tagOption(word, "length", state.length === word, true)).join("")}</div></fieldset>`;
  if (stage === 3) content = `<p class="step-number">03.</p><h1 class="step-title">也可以，认识你的手。</h1><p class="step-description">加一张手背照片，也可以跳过。</p><div class="field">${uploadBox("own", "添加一张清晰手背照片，可跳过")}</div>${note("正式版可将照片交给视觉模型提取特点，原照片默认本地保存，特点关键词同步云端。此预览不分析、不上传，也不把照片写入本地持久存储。")}`;
  if (stage === 4) content = `<p class="step-number">04.</p><h1 class="step-title">这份描述，像你吗？</h1><p class="step-description">描述应帮助你表达喜好，而不是限制你的选择。</p><div class="field"><label for="onboarding-summary">偏好描述，可直接修改</label><textarea id="onboarding-summary" data-draft="onboardingSummaryDraft" maxlength="600">${esc(state.onboardingSummaryDraft ?? preferenceText())}</textarea><small>选项模板 · 可修改</small></div><label class="switch-row"><input type="checkbox" id="onboarding-learn" ${state.onboardingLearnDraft ? "checked" : ""}>逐渐了解我的偏好（未来功能）</label>`;
  return `${link("home", `${icon("back")} 随时回去逛逛`, "back-link")}<div class="onboard-layout"><div class="onboard-photo"><img src="${photo(2)}" alt="法式美甲的氛围参考，AI 演示素材"><span class="image-label">A LITTLE MORE YOU · AI 灵感</span></div><section class="onboard-form"><p class="eyebrow coral">A LITTLE MORE YOU · ${stage} / 4</p><div class="progress-line"><span style="width:${stage * 25}%"></span></div><form id="onboarding-form" data-step="${stage}">${content}<div class="action-row">${stage > 1 ? link(`onboarding/${stage - 1}`, "上一步", "secondary") : ""}<button class="primary" type="submit">${stage === 4 ? "保存偏好，去遇见喜欢" : stage === 3 && !state.uploads.own ? "暂不加照片，继续" : "继续"} ${icon("arrow")}</button></div></form>${action("skip-onboarding", "先逛逛，之后再了解", "text-button")}</section></div>`;
}
function render() {
  if (composingField?.isConnected && (location.hash.slice(1) || "home") === renderedHash) { deferredRender = true; return; }
  const active = focusIdentity();
  const selection = typeof document.activeElement?.selectionStart === "number" ? { start: document.activeElement.selectionStart, end: document.activeElement.selectionEnd, direction: document.activeElement.selectionDirection } : null;
  const y = window.scrollY;
  const hash = location.hash.slice(1) || "home";
  const routeChanged = hash !== renderedHash;
  const [route, parameter] = location.hash.slice(1).split("/");
  currentRoute = route || "home";
  const views = { home, tryon, photo: photoTryon, camera, create, me, profile, saved, publish, look: () => detail(parameter), scheme: () => scheme(parameter), creator: () => creator(parameter === "me"), onboarding: () => onboarding(parameter) };
  routeAnimation?.cancel();
  shell((Object.hasOwn(views, currentRoute) ? views[currentRoute] : home)());
  document.title = `${({ home: "为你", tryon: "试戴", create: "创作", me: "我的", onboarding: "了解你的偏好", scheme: "我的美甲方案" })[currentRoute] ?? "灵感空间"} · 甲如设计提案`;
  if (routeChanged || focusAfterRoute) {
    const target = pendingNavigation?.restore ? scrollPositions.get(hash) ?? 0 : 0;
    window.scrollTo(0, target);
    $("#main").focus({ preventScroll: true });
    routeAnimation = motion($(".page-view"), [{ opacity: .3, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 300 });
  } else {
    if (active) {
      const target = $(active);
      target?.focus({ preventScroll: true });
      if (selection) target?.setSelectionRange?.(selection.start, selection.end, selection.direction);
    }
    window.scrollTo(0, y);
  }
  renderedHash = hash;
  pendingNavigation = undefined;
  focusAfterRoute = false;
  revealCards();
  updateViewport();
  if (currentRoute === "scheme") prepareScheme(parameter);
}
function showLogin(then) {
  modal("先体验登录后的空间", `<p>这是独立设计提案，不连接真实登录服务。继续后只切换本地模拟状态，不代表账号已认证，也不会开启云同步。</p><div class="action-row">${action("simulate-login", "进入模拟登录态", "primary", then ? `data-then="${then}"` : "")}</div>`);
}
function toggle(list, id) {
  if (state[list].includes(id)) state[list] = state[list].filter((value) => value !== id);
  else state[list].push(id);
  persist();
}
function simulateGeneration(mode) {
  if (mode === "photo" && !state.uploads[state.otherPerson ? "other" : "own"]) { toast("请先添加本次手部照片。照片仅在本地预览。"); return; }
  if (mode === "create" && !state.createDraft.trim()) { toast("先写一点喜欢的颜色或感觉，也可以点选灵感词。"); return; }
  clearTimeout(jobTimers[mode]);
  state.generationByMode[mode] = "loading";
  state.resultLooks[mode] = state.selectedLook;
  focusAfterRoute = false;
  render();
  jobTimers[mode] = setTimeout(() => {
    state.generationByMode[mode] = "ready";
    if (currentRoute === mode) render();
  }, 1100);
}
async function validateUpload(file) {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("请选择 JPG、PNG 或 WebP 图片。");
  if (file.size > 10 * 1024 * 1024) throw new Error("图片超过 10 MB，请换一张较小的照片。");
  let size;
  if (typeof createImageBitmap === "function") {
    const image = await createImageBitmap(file);
    size = { width: image.width, height: image.height }; image.close();
  } else {
    const url = URL.createObjectURL(file);
    try { const image = new Image(); image.src = url; await image.decode(); size = { width: image.naturalWidth, height: image.naturalHeight }; }
    finally { URL.revokeObjectURL(url); }
  }
  const valid = size.width >= 320 && size.height >= 320 && size.width <= 4096 && size.height <= 4096;
  if (!valid) throw new Error("图片宽高需各为 320–4096 像素，请换一张清晰照片。");
}
async function buildSchemeFile(id) {
  const look = byId(id);
  const description = state.schemeOrigin === "create" ? state.createDraft : state.photoDraft;
  const length = state.length;
  const scenes = state.scenes.join("、") || look.scene;
  const image = new Image();
  image.src = photo(look.id);
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = 1000; canvas.height = 1540;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("当前浏览器不能创建方案图片，可复制文字。");
  ctx.fillStyle = "#f7f4ee"; ctx.fillRect(0, 0, 1000, 1540);
  ctx.fillStyle = "#292a27"; ctx.font = "italic 52px Georgia"; ctx.fillText("JiaRu", 70, 100);
  ctx.font = "18px sans-serif"; ctx.fillText("MY NAIL NOTE / 美甲方案参考", 580, 94);
  ctx.drawImage(image, 70, 145, 860, 860);
  await document.fonts?.load('400 36px "JiaRu Editorial"');
  ctx.font = '400 36px "JiaRu Editorial", serif'; ctx.fillText(look.name, 70, 1080);
  ctx.font = "22px sans-serif";
  const lines = [`风格：${look.original} / ${look.tag}`, `长度：${length}    场景：${scenes}`, `补充：${description || "请结合实际甲面与美甲师建议调整。"}`];
  let y = 1140;
  for (const line of lines) {
    let current = "";
    for (const char of line) {
      if (ctx.measureText(current + char).width > 850) { if (y > 1410) break; ctx.fillText(current, 70, y); y += 38; current = ""; }
      current += char;
    }
    if (y <= 1410) { ctx.fillText(current, 70, y); y += 45; }
  }
  ctx.fillStyle = "#ac5145"; ctx.font = "18px sans-serif"; ctx.fillText("AI 演示款式 · 非本次生成 · 非实际制作效果 · JIARU", 70, 1480);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("方案图片生成失败，可重试或复制文字。");

  return new File([blob], `甲如美甲方案-${look.original}.png`, { type: "image/png" });
}
function schemeKey(id) {
  return JSON.stringify([byId(id).id, state.length, state.scenes, state.schemeOrigin, state.schemeOrigin === "create" ? state.createDraft : state.photoDraft]);
}
function prepareScheme(id) {
  const key = schemeKey(id);
  if (!schemeFiles.has(key)) {
    if (schemeFiles.size >= 3) schemeFiles.delete(schemeFiles.keys().next().value);
    const record = { file: null, promise: null };
    record.promise = buildSchemeFile(id).then((file) => { record.file = file; return file; });
    schemeFiles.set(key, record);
  }
  const record = schemeFiles.get(key);
  record.promise.then(() => {
    if (currentRoute === "scheme" && $('[data-action="share-scheme"]')?.dataset.id === String(byId(id).id) && schemeKey(id) === key) {
      const button = $('[data-action="share-scheme"]');
      if (button) { button.disabled = false; button.removeAttribute("aria-busy"); }
    }
  }).catch(() => {
    schemeFiles.delete(key);
    if (currentRoute === "scheme") toast("方案图片暂未准备好，可保存重试或复制文字。");
  });
  return record;
}
function saveSchemeFile(file) {
  const url = URL.createObjectURL(file); exportUrls.add(url);
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = file.name;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => { URL.revokeObjectURL(url); exportUrls.delete(url); }, 60000);
  toast("方案图片已准备保存。");
}
async function downloadScheme(id) { saveSchemeFile(await prepareScheme(id).promise); }
async function shareScheme(id) {
  const record = prepareScheme(id);
  if (!record.file) { toast("方案图片正在准备，请稍后再试。"); return; }
  if (typeof navigator.share !== "function" || !navigator.canShare?.({ files: [record.file] })) { saveSchemeFile(record.file); return; }
  try { await navigator.share({ files: [record.file], title: "我的美甲方案", text: "甲如 · AI 灵感参考，非实际制作效果" }); toast("已交给系统分享面板。"); }
  catch (error) { if (error.name !== "AbortError") { saveSchemeFile(record.file); } }
}
function updateViewport() {
  const viewport = window.visualViewport;
  const field = document.activeElement;
  const editing = field?.matches?.('textarea:not([readonly]), input:not([readonly]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=button]):not([type=submit])');
  const inset = viewport ? Math.max(0, innerHeight - viewport.height - viewport.offsetTop) : 0;
  const keyboard = Boolean(viewport && editing && Math.abs(viewport.scale - 1) < .02 && inset > Math.max(120, innerHeight * .18));
  document.body.classList.toggle("keyboard-open", keyboard);
  document.documentElement.style.setProperty("--keyboard-inset", keyboard ? `${inset}px` : "0px");
}
function closeModal() { $("#sheet").close(); }
function updateSearch() {
  const results = $("#look-results");
  if (!results) return;
  results.innerHTML = lookResults(); revealCards();
}

document.addEventListener("click", async (event) => {
  const anchor = event.target.closest("a[href^='#']");
  if (anchor && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
    event.preventDefault();
    if (anchor.classList.contains("skip-link")) { $("#main").focus({ preventScroll: true }); return; }
    $("#sheet").close();
    navigate(anchor.getAttribute("href").slice(1), { restore: anchor.classList.contains("back-link") || anchor.hasAttribute("data-return-editor") });
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const name = button.dataset.action;
  focusAfterRoute = false;
  try {
    if (name === "close-modal") closeModal();
    if (name === "save" || name === "like") {
      toggle(name === "save" ? "saved" : "liked", byId(button.dataset.id).id);
      const y = window.scrollY;
      render(); window.scrollTo(0, y);
      const updated = $(`[data-action="${name}"][data-id="${button.dataset.id}"]`);
      updated?.classList.toggle(name === "save" ? "is-saved" : "is-liked", updated.getAttribute("aria-pressed") === "true");
      motion(updated, [{ transform: "scale(.86)" }, { transform: "scale(1.07)" }, { transform: "scale(1)" }], { duration: 260 });
      toast(name === "save" ? "收藏已更新" : "喜欢已更新");
    }
    if (name === "follow") {
      if (!state.loggedIn) showLogin("follow");
      else { state.following = !state.following; persist(); render(); toast("预览关注状态已更新，未连接真实账号。"); }
    }
    if (name === "simulate-login") { state.loggedIn = true; if (button.dataset.then === "follow") { state.following = true; persist(); } $("#sheet").close(); render(); toast("已进入模拟登录态，尚无云同步。"); }
    if (name === "login") showLogin();
    if (name === "filter") { state.filter = button.dataset.filter; const y = window.scrollY; render(); window.scrollTo(0, y); }
    if (name === "prompt") { state.createDraft = state.createDraft ? `${state.createDraft}，${button.dataset.prompt}`.slice(0, 300) : button.dataset.prompt; render(); }
    if (name === "generate") simulateGeneration(button.dataset.mode);
    if (name === "skip-onboarding") { state.onboarded = true; persist(); navigate("home"); toast("可以先随意逛逛，之后在“我的”补充偏好。"); }
    if (name === "cloud-info") modal("你的照片，与你的偏好", "<p>已确认的正式版方向：手部原照片默认本地；特点关键词、偏好和作品支持登录后跨设备。为他人使用不覆盖主人手部档案。</p><p>此提案没有云端接口。文字与收藏只写入独立本地预览空间；上传图片仅存内存，关闭或刷新页面后需重新选择。</p>");
    if (name === "camera-info") modal("摄像头流程提案", "<p>正式版流程：主动点击开启 → 浏览器询问权限 → 加载识别资源 → 放入手背 → 选择颜色或纹理。</p><p>权限被拒绝时，说明如何重新授权，并始终提供照片入口。当前提案不申请权限，也未启动摄像头。</p>");
    if (name === "camera-color") toast(`已选择${byId(button.dataset.id).original}，摄像头仍未开启。`);
    if (name === "advanced") modal("生成设置的位置", "<p>普通用户先表达想法。画面比例、尺寸与引擎放入次级设置，保留默认值，并说明不同服务的费用和等待时间。</p><p>当前未选择模型服务，此提案不展示未经实测的价格或速度承诺。</p>");
    if (name === "show-notes") modal("这是一份可交互设计提案", "<p>已经可体验：页面导航、轻问答、偏好模板与纠正、本地收藏、上传预览、模拟登录后的发布布局、方案卡下载。</p><p>尚未接入：语言模型、真实生成、自动推荐、跨设备同步、真实登录、公开发布与关注、摄像头和 AR。全部图片为既有 AI 演示素材。</p><p>旧版页面、账户数据库和模型发布状态保持原状。</p>");
    if (name === "show-error") { clearTimeout(jobTimers.create); state.generationByMode.create = "error"; if (currentRoute === "create") render(); else navigate("create"); }
    if (name === "empty") modal("还没有内容，也不必着急", `<p>收藏为空时应说明下一步，发布为空时应邀请创作，而不是用假数据填充。</p>${empty("第一份心动，还在等你", "去发现喜欢，或开始一份新的创作。", link("home", "去发现", "primary"))}`);
    if (name === "wireframe") document.body.classList.toggle("wireframe");
    if (name === "reset") modal("重置这份预览？", `<p>仅删除此提案的偏好和收藏，清空本次图片与草稿。旧版数据不受影响。</p><div class="action-row">${action("confirm-reset", "重置本地预览", "primary")}</div>`);
    if (name === "confirm-reset") { localStorage.removeItem(storageKey); releaseUploads(); location.hash = "home"; location.reload(); }
    if (name === "download-scheme") await downloadScheme(button.dataset.id);
    if (name === "share-scheme") await shareScheme(button.dataset.id);
    if (name === "copy-scheme") {
      const look = byId(button.dataset.id);
      const text = `甲如美甲方案\n${look.name} / ${look.original}\n长度：${state.length}\n场景：${state.scenes.join("、") || look.scene}\n补充：${(state.schemeOrigin === "create" ? state.createDraft : state.photoDraft) || "请结合实际甲面和美甲师建议调整。"}\nAI 演示参考，非真实制作效果。`;
      try { await navigator.clipboard.writeText(text); toast("方案文字已复制。"); }
      catch { modal("复制美甲方案", `<p>当前浏览器不允许自动复制，可以选择下方文字手动复制。</p><textarea readonly aria-label="方案文字">${esc(text)}</textarea>`); }
    }
  } catch (error) { toast(error instanceof Error ? error.message : "操作未完成，请重试。"); }
});

document.addEventListener("compositionstart", (event) => { composingField = event.target; if (event.target.id === "look-search") searchComposing = true; });
document.addEventListener("compositionend", (event) => {
  composingField = null;
  if (event.target.dataset.draft) state[event.target.dataset.draft] = event.target.value;
  if (event.target.id === "look-search") { searchComposing = false; state.query = event.target.value; updateSearch(); }
  if (deferredRender) { deferredRender = false; requestAnimationFrame(() => render()); }
});
document.addEventListener("input", (event) => {
  if (event.target.dataset.draft) state[event.target.dataset.draft] = event.target.value;
  if (event.target.id === "look-search") {
    state.query = event.target.value;
    if (!searchComposing && !event.isComposing) updateSearch();
  }
});
document.addEventListener("change", async (event) => {
  const input = event.target;
  if (input.id === "other-person") { state.otherPerson = input.checked; clearTimeout(jobTimers.photo); state.generationByMode.photo = "idle"; render(); }
  if (input.id === "selected-look") { state.selectedLook = byId(input.value).id; clearTimeout(jobTimers.photo); state.generationByMode.photo = "idle"; render(); }
  if (input.id === "learn-toggle") state.profileLearnDraft = input.checked;
  if (input.id === "onboarding-learn") state.onboardingLearnDraft = input.checked;
  if (input.id === "publish-rights") state.publishRights = input.checked;
  if (input.id === "publish-source") state.publishSource = input.value;
  if (["styles", "scenes"].includes(input.name)) state[input.name] = [...document.querySelectorAll(`input[name="${input.name}"]:checked`)].map((item) => item.value);
  if (input.name === "length") state.length = input.value;
  if (input.dataset.upload && input.files[0]) {
    const slot = input.dataset.upload;
    const sequence = (uploadSequence[slot] ?? 0) + 1; uploadSequence[slot] = sequence;
    try {
      const file = input.files[0];
      await validateUpload(file);
      if (uploadSequence[slot] !== sequence) return;
      if (state.uploads[slot]) URL.revokeObjectURL(state.uploads[slot].url);
      state.uploads[slot] = { name: file.name, url: URL.createObjectURL(file) };
      const mode = slot === "reference" ? "create" : ["own", "other"].includes(slot) ? "photo" : null;
      if (mode) { clearTimeout(jobTimers[mode]); state.generationByMode[mode] = "idle"; }
      focusAfterRoute = false; render(); toast("照片仅已加入本次本地预览，没有上传。");
    } catch (error) { input.value = ""; toast(error.message || "图片解码失败，请更换照片。"); }
  }
});
document.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  focusAfterRoute = false;
  if (form.id === "onboarding-form") {
    const step = Number(form.dataset.step);
    if (step < 4) navigate(`onboarding/${step + 1}`);
    else { state.profile = $("#onboarding-summary").value.trim(); state.learned = $("#onboarding-learn").checked; state.profileDraft = state.profile; state.profileLearnDraft = state.learned; state.onboarded = true; persist(); navigate("home"); toast("偏好已保存到本地预览，未调用语言模型。"); }
  }
  if (form.id === "profile-form") { state.profile = $("#profile-text").value.trim(); state.learned = $("#learn-toggle").checked; state.profileDraft = state.profile; persist(); toast("偏好已更新到本地预览。"); }
  if (form.id === "publish-form") {
    if (!state.loggedIn) { showLogin(); return; }
    if (!state.uploads.publish) { toast("请先添加款式图片。"); return; }
    if (!$("#publish-rights").checked) { toast("请确认图片分享权利。"); return; }
    const title = $("#publish-title").value.trim();
    if (!title) { toast("请给作品起一个名字。"); return; }
    state.posts.push({ title, source: state.publishSource, description: $("#publish-text").value.trim(), url: state.uploads.publish.url });
    // 转移 URL 所有权，后续换图不会释放已发布的本地预览图片。
    state.uploads.publish = null; state.publishTitle = ""; state.publishDraft = ""; state.publishRights = false;
    navigate("creator/me"); toast("本地发布布局已生成，照片没有上传或公开。");
  }
});
function releaseUploads() {
  for (const upload of Object.values(state.uploads)) if (upload) URL.revokeObjectURL(upload.url);
  for (const post of state.posts) URL.revokeObjectURL(post.url);
}
window.addEventListener("hashchange", () => {
  if (!pendingNavigation) { scrollPositions.set(renderedHash, window.scrollY); pendingNavigation = { restore: true }; }
  $("#sheet").close(); focusAfterRoute = true; render();
});
$("#sheet").addEventListener("close", () => {
  document.body.classList.remove("sheet-open");
  if (modalTrigger) { $(modalTrigger)?.focus({ preventScroll: true }); modalTrigger = null; }
  updateViewport();
});
$("#sheet").addEventListener("click", (event) => {
  if (event.target !== event.currentTarget) return;
  const box = event.currentTarget.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeModal();
});
document.addEventListener("keydown", (event) => { if (event.key === "Tab" || event.key.startsWith("Arrow")) document.body.dataset.input = "keyboard"; });
document.addEventListener("pointerdown", (event) => {
  document.body.dataset.input = ["touch", "pen"].includes(event.pointerType) ? "touch" : "mouse";
  const control = event.target.closest("button, .primary, .secondary, .chip");
  if (control && !control.disabled) motion(control, [{ transform: "scale(1)" }, { transform: "scale(.97)" }, { transform: "scale(1)" }], { duration: 180 });
}, { passive: true });
document.addEventListener("focusin", updateViewport);
document.addEventListener("focusout", () => requestAnimationFrame(updateViewport));
window.visualViewport?.addEventListener("resize", updateViewport, { passive: true });
window.visualViewport?.addEventListener("scroll", updateViewport, { passive: true });
window.addEventListener("resize", updateViewport, { passive: true });
reducedMotion.addEventListener?.("change", () => {
  if (reducedMotion.matches) { document.getAnimations().forEach((animation) => animation.cancel()); revealObserver?.disconnect(); }
});
window.addEventListener("pagehide", (event) => { if (!event.persisted) { Object.values(jobTimers).forEach(clearTimeout); exportUrls.forEach((url) => URL.revokeObjectURL(url)); revealObserver?.disconnect(); releaseUploads(); } });
render();
