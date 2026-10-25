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
  loggedIn: false, cameraColor: null, filter: "全部", query: "", otherPerson: false,
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
/* 勾选逐笔绘制（动效方案 §2.5）：对钩常驻 DOM 保证布局稳定；pathLength=100 归一化后仅过渡 dashoffset */
const checkIcon = '<svg class="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="check-path" pathLength="100" d="m5 12 4 4L20 5"/></svg>';
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
/* ===== 动效优化方案实现（docs/consumer-redesign-motion-plan.md）=====
   统一原则：原地弹性（无静态位移）、阴影不形变、反馈跟随指针、
   spring 过冲＋squash & stretch 两种物理、联动元件同频、降级一致。 */
const motionRandom = () => (window.__jiaruMotionRandom ?? Math.random)();
/* 按压回弹（§2.1）：按下加 is-pressed（CSS 140ms 下沉 scale(.96)）；
   释放播放显式三段关键帧 .96 → 1.026 → 1（越过原始尺寸约 2.5% 再落位）；
   键盘路径同参；重新按下时取消未完成回弹，避免两次回弹叠加 */
const pressTargets = ".primary, .secondary, .chip, .round-button, .icon-action, .save-button, .mode-card .text-button";
const pressFrames = [{ transform: "scale(.96)" }, { transform: "scale(1.026)" }, { transform: "scale(1)" }];
const pressTiming = { duration: 340, easing: "cubic-bezier(.34,1.56,.64,1)" };
function pressControl(control) {
  if (!control || control.disabled) return;
  control.getAnimations().forEach((animation) => { if (animation.id === "press-rebound") animation.cancel(); });
  control.classList.add("is-pressed");
}
function releasePress(control) {
  if (!control?.classList.contains("is-pressed")) return;
  control.classList.remove("is-pressed");
  if (reducedMotion.matches || !control.animate) return;
  const animation = control.animate(pressFrames, pressTiming);
  animation.id = "press-rebound";
}
function releaseAllPress() { document.querySelectorAll(`${pressTargets}.is-pressed`).forEach(releasePress); }
/* 水波按钮（§2.3）：落点为原点，半径覆盖最远角；z-index:-1 位于底色之上、文字之下 */
const rippleTargets = pressTargets;
function spawnRipple(control, clientX, clientY) {
  if (reducedMotion.matches || !control?.animate) return;
  const ripples = control.querySelectorAll(".ripple");
  if (ripples.length >= 3) ripples[0].remove();
  const rect = control.getBoundingClientRect();
  const x = (clientX ?? rect.left + rect.width / 2) - rect.left;
  const y = (clientY ?? rect.top + rect.height / 2) - rect.top;
  const radius = Math.hypot(Math.max(x, rect.width - x), Math.max(y, rect.height - y)) * 1.02;
  const ripple = document.createElement("span");
  ripple.className = "ripple";
  ripple.style.left = `${x - radius}px`;
  ripple.style.top = `${y - radius}px`;
  ripple.style.width = `${radius * 2}px`;
  ripple.style.height = `${radius * 2}px`;
  control.append(ripple);
  const animation = ripple.animate(
    [{ transform: "scale(0)", opacity: .3 }, { transform: "scale(1)", opacity: .3, offset: .7 }, { transform: "scale(1)", opacity: 0 }],
    { duration: 480, easing: "cubic-bezier(.22,.7,.2,1)" },
  );
  animation.onfinish = () => ripple.remove();
  animation.oncancel = () => ripple.remove();
}
/* 关键动作爆散（§2.4）：轻/中/重三档，粒子数、射程、粒径、时长与成功分量匹配；失败不爆散 */
const burstTiers = {
  light: { count: [8, 10], range: [18, 28], size: [3, 4], duration: 420, colors: ["#ac5145", "#884338"] },
  medium: { count: [12, 14], range: [32, 44], size: [3, 5], duration: 520, colors: ["#ac5145", "#a34b3f", "#e3e7dd"] },
  heavy: { count: [16, 18], range: [48, 60], size: [4, 6], duration: 620, colors: ["#ac5145", "#884338", "#a34b3f", "#e3e7dd"] },
};
const burstThrottle = new WeakMap();
function burstAt(x, y, tier = "light") {
  if (reducedMotion.matches || !Number.isFinite(x) || !Number.isFinite(y)) return;
  const spec = burstTiers[tier] ?? burstTiers.light;
  const layer = document.createElement("div");
  layer.className = "burst-layer";
  document.body.append(layer);
  const count = spec.count[0] + Math.floor(motionRandom() * (spec.count[1] - spec.count[0] + 1));
  let finished = 0;
  for (let index = 0; index < count; index += 1) {
    const angle = (index / count) * Math.PI * 2 + (motionRandom() - .5) * .6;
    const distance = spec.range[0] + motionRandom() * (spec.range[1] - spec.range[0]);
    const size = spec.size[0] + motionRandom() * (spec.size[1] - spec.size[0]);
    const particle = document.createElement("span");
    particle.className = "burst-particle";
    particle.style.left = `${x}px`;
    particle.style.top = `${y}px`;
    particle.style.width = `${size}px`;
    particle.style.height = `${size}px`;
    particle.style.marginLeft = `${-size / 2}px`;
    particle.style.marginTop = `${-size / 2}px`;
    particle.style.background = spec.colors[index % spec.colors.length];
    layer.append(particle);
    const animation = particle.animate(
      [
        { transform: "translate(0,0) scale(1)", opacity: 1, offset: 0 },
        { transform: `translate(${Math.cos(angle) * distance * .72}px, ${Math.sin(angle) * distance * .72 - 4}px) scale(.85)`, opacity: 1, offset: .62 },
        { transform: `translate(${Math.cos(angle) * distance}px, ${Math.sin(angle) * distance - 6}px) scale(.2)`, opacity: 0, offset: 1 },
      ],
      { duration: spec.duration, easing: "cubic-bezier(.22,.7,.2,1)", fill: "forwards" },
    );
    const done = () => { finished += 1; if (finished === count) layer.remove(); };
    animation.onfinish = done;
    animation.oncancel = done;
  }
}
function burst(control, tier = "light", point = null) {
  if (!control || reducedMotion.matches) return;
  const now = performance.now();
  if ((burstThrottle.get(control) ?? 0) > now - 250) return;
  burstThrottle.set(control, now);
  const rect = control.getBoundingClientRect();
  if (point) burstAt(point.x, point.y, tier);
  else if (rect.width > 0) burstAt(rect.left + rect.width / 2, rect.top + rect.height / 2, tier);
}
/* 弹性开关滑块（§2.2）：起步横拉 120ms→回落→落位微压回；位移与形变由 @property 分别过渡 */
function playSwitchElastic(row) {
  if (!row || reducedMotion.matches) return;
  clearTimeout(row.__stretchOff);
  clearTimeout(row.__settleOff);
  row.classList.remove("is-settling");
  row.classList.add("is-stretching");
  row.__stretchOff = setTimeout(() => {
    row.classList.remove("is-stretching");
    row.__settleOff = setTimeout(() => {
      row.classList.add("is-settling");
      row.__settleOff = setTimeout(() => row.classList.remove("is-settling"), 80);
    }, 120);
  }, 120);
}
/* 数字滚动（§2.7）：每位固定行高溢出容器；位序越高启动越晚、时长越长；强减速自然停止 */
const statPrevious = new Map();
function buildDigit(digit) {
  const wrapper = document.createElement("span");
  wrapper.className = "digit";
  const column = document.createElement("span");
  column.className = "digit-column";
  for (let value = 0; value < 10; value += 1) {
    const cell = document.createElement("span");
    cell.textContent = String(value);
    column.append(cell);
  }
  column.style.transform = `translateY(${-digit * 1.2}em)`;
  wrapper.append(column);
  return wrapper;
}
function rollNumber(strong, from, to) {
  const next = String(to);
  const digits = next.split("");
  const previous = String(from).padStart(digits.length, "0").split("");
  strong.textContent = "";
  if (reducedMotion.matches || !strong.animate) { strong.textContent = next; return; }
  digits.forEach((digit, index) => {
    const fromDigit = Number(previous[index] ?? 0);
    const toDigit = Number(digit);
    const element = buildDigit(toDigit);
    element.firstElementChild.style.transform = `translateY(${-fromDigit * 1.2}em)`;
    strong.append(element);
    if (fromDigit === toDigit || Math.abs(toDigit - fromDigit) > 5) return;
    const positions = digits.length - index;
    element.firstElementChild.animate(
      [{ transform: `translateY(${-fromDigit * 1.2}em)` }, { transform: `translateY(${-toDigit * 1.2}em)` }],
      { duration: 320 + (positions - 1) * 100, delay: (positions - 1) * 80, easing: "cubic-bezier(.16,.84,.34,1)", fill: "forwards" },
    );
  });
}
/* 局部重渲染会移除原按钮（含其中的水波）：在新元件上按原坐标补一次，保持反馈完整 */
function respawnRipple(control, clientX, clientY, detail) {
  const target = typeof control === "string" ? $(control) : control;
  if (!target) return;
  if (detail) spawnRipple(target, clientX, clientY);
  else spawnRipple(target);
}
function upgradeStats() {
  document.querySelectorAll(".stats .stat-value").forEach((strong) => {
    const key = strong.dataset.stat;
    const next = strong.textContent.trim();
    const previous = statPrevious.get(key);
    statPrevious.set(key, next);
    if (previous === undefined || previous === next) {
      if (!reducedMotion.matches && strong.animate) {
        strong.textContent = "";
        next.split("").forEach((digit) => strong.append(buildDigit(Number(digit))));
      }
      return;
    }
    rollNumber(strong, previous, next);
  });
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

function persist({ quiet = false } = {}) {
  const data = Object.fromEntries(["saved", "liked", "following", "profile", "styles", "scenes", "length", "learned", "onboarded"].map((key) => [key, state[key]]));
  try { localStorage.setItem(storageKey, JSON.stringify(data)); return true; }
  catch {
    storageAvailable = false;
    /* 喜欢/收藏需要按操作给出各自的失败文案，故允许调用方静默取回结果后自行提示 */
    if (!quiet) toast("浏览器未能保存预览数据，本次会话仍可继续；请勿将它视为已持久保存。");
    return false;
  }
}
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4400);
}
function modal(title, body) {
  const dialog = $("#sheet");
  if (modalExit) { const aborted = modalExit; modalExit = null; aborted.cancel(); }
  modalTrigger = { selector: focusIdentity(), hash: renderedHash };
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
  $("#app").innerHTML = `<header class="site-header"><a class="brand" href="#home" aria-label="甲如，为你"><span class="wordmark">JiaRu<span class="brand-sub">nail atelier</span></span><span class="brand-cn">甲如</span></a><nav class="desktop-links" aria-label="主导航">${navigation.top}</nav><div class="header-actions">${link("profile", icon("settings"), "round-button", 'aria-label="我的偏好"')}${link("saved", icon("bookmark"), "round-button", 'aria-label="我的收藏"')}</div></header><main id="main" tabindex="-1"><div class="page-view">${content}${!storageAvailable ? note("本地存储不可用，当前内容仅保留在本次会话。") : ""}</div><footer class="footer-note"><span>JiaRu · 指尖的日常美学</span>${action("show-notes", `${icon("info")} 关于预览`, "icon-action", 'aria-label="能力与数据边界"')}</footer><details class="scenario-toolbar"><summary>${icon("settings")} 预览设置</summary><div class="scenario-actions">${action("show-error", "失败状态", "text-button")}${action("empty", "空内容", "text-button")}${action("wireframe", "线框视图", "text-button")}${action("motion-demo", "动效演示", "text-button")}${action("reset", "重置本地预览", "text-button")}</div></details></main><nav class="bottom-nav" aria-label="主导航">${navigation.bottom}</nav>`;
}
function lookCard(look) {
  const saved = state.saved.includes(look.id);
  return `<article class="look-card"><div class="look-cover"><a href="#look/${look.id}" aria-label="查看${look.name}"><img src="${photo(look.id)}" alt="${look.original}，AI 演示款式" loading="lazy" width="500" height="625"></a><span class="image-label">AI 灵感</span>${action("save", icon("bookmark"), `save-button${saved ? " is-saved" : ""}`, `data-id="${look.id}" data-reaction-name="${look.name}" aria-label="${saved ? "取消收藏" : "收藏"}${look.name}" aria-pressed="${saved}"`)}</div><div class="card-title-row"><h3>${link(`look/${look.id}`, look.name, "")}</h3><span class="color-dots" aria-hidden="true">${look.colors.map((color) => `<i style="background:${color}"></i>`).join("")}</span></div><p class="card-caption">${look.tag} · ${look.scene}</p></article>`;
}
function home() {
  const hero = `<section class="hero"><div class="hero-copy"><p class="eyebrow coral season-label">THE EVERYDAY MUSE</p><h1>把喜欢的自己，<br>留在<em>每一次抬手。</em></h1><p class="hero-desc">让喜欢，轻轻落在指尖。</p>${link("tryon", `开始试戴 ${icon("arrow")}`, "primary")}</div><div class="hero-art" aria-label="本期纤细手背与五种精致美甲灵感"><img class="main-photo" src="/assets/hero-hand-diversity-v3.png" alt="纤细白皙的手背，五指分别展示短圆冰透、长梯形猫眼、椭圆贝母、尖杏仁碎钻与短方圆几何美甲，AI 拼贴主视觉" width="1122" height="1402" fetchpriority="high"><span class="art-number">JIARU EDIT / 01 · AI 灵感</span><i class="art-dot"></i><span class="art-caption">A little more you.</span></div></section>`;
  return `${hero}<aside class="onboarding-callout"><span class="callout-mark">${icon("sparkle")}</span><div class="callout-copy"><h2>找到你的风格</h2><p>${state.profile ? esc(state.profile.slice(0, 35)) : "从几个喜欢的词开始。"}</p></div>${link("onboarding/1", `${icon("arrow")}`, "text-button", 'aria-label="了解或调整我的偏好"')}</aside><div class="section-heading"><div><p class="eyebrow muted">CURATED FOR YOU</p><h2>此刻心动</h2></div>${link("saved", icon("bookmark"), "round-button", 'aria-label="查看我的收藏"')}</div><div class="search-box">${icon("search")}<input type="search" id="look-search" placeholder="法式、裸粉、通勤…" aria-label="搜索款式" value="${esc(state.query)}"></div><div class="filters-wrap"><div class="filters" role="group" aria-label="款式分类">${action("filter", "全部", "chip", `data-filter="全部" aria-pressed="${state.filter === "全部"}"`)}<span class="filter-group" role="group" aria-label="按风格筛选">${["自然", "简约", "轻闪", "复古"].map((tag) => action("filter", tag, "chip", `data-filter="${tag}" aria-pressed="${state.filter === tag}"`)).join("")}</span><span class="filter-group" role="group" aria-label="按场景筛选">${["日常", "通勤", "约会", "出游", "聚会", "婚礼"].map((tag) => action("filter", tag, "chip", `data-filter="${tag}" aria-pressed="${state.filter === tag}"`)).join("")}</span></div></div><div id="look-results" aria-live="polite">${lookResults()}</div>`;
}
function lookResults() {
  const filtered = looks.filter((look) => (state.filter === "全部" || look.tag === state.filter || look.scene === state.filter) && `${look.name}${look.original}${look.tag}${look.scene}`.includes(state.query.trim()));
  return filtered.length ? `<div class="look-grid">${filtered.map(lookCard).join("")}</div>` : empty("还没有找到这份心动", "换个词，或创造一点新灵感。", link("create", "去创作", "primary"));
}
function empty(title, description, buttons = "") { return `<section class="empty-state">${icon("sparkle")}<h2>${title}</h2><p>${description}</p>${buttons}</section>`; }
function tryon() {
  return `${intro("A LOOK ON YOU", "指尖，换一种心情", "选一种方式，开始试戴。")}<div class="switch-block${state.otherPerson ? " is-on" : ""}"><label class="switch-row"><input type="checkbox" id="other-person" ${state.otherPerson ? "checked" : ""}><span class="switch-knob" aria-hidden="true"></span>为身边的人试戴</label><p class="inline-note switch-note">沿用你的审美，只更换本次照片，不覆盖本人档案。</p></div><div class="choice-grid"><a href="#photo" class="mode-card" aria-label="用一张照片"><span class="mode-illustration">${icon("photo")}</span><p class="eyebrow mode-eyebrow">PHOTO TRY-ON</p><h2>照片试戴</h2><p>AI 上手参考</p><span class="text-button" aria-hidden="true">${icon("arrow")}</span></a><a href="#camera" class="mode-card" aria-label="打开摄像头"><span class="mode-illustration">${icon("camera")}</span><p class="eyebrow mode-eyebrow">LIVE TRY-ON</p><h2>摄像头试戴</h2><p>实时 AR · 流程预览</p><span class="text-button" aria-hidden="true">${icon("arrow")}</span></a></div>${note("设计预览不会上传照片或启动摄像头，真实 AI 与 AR 尚未接入。")}`;
}
function uploadBox(slot, label) {
  const uploaded = state.uploads[slot];
  return `<label class="upload-box">${uploaded ? `<img src="${uploaded.url}" alt="${label}，仅本次本地预览">${esc(uploaded.name)}` : `${icon("upload")}<span>${label}</span><small>JPG / PNG / WebP · 最多 10 MB</small>`}<input type="file" accept="image/jpeg,image/png,image/webp" data-upload="${slot}" aria-label="${label}"></label>`;
}
function resultPanel(mode) {
  /* 骨架落位高度契约（动效方案 §2.8）：与 ready 的 .sample-result 同模板同 spacing——
     图片 4/5 aspect、说明行 44px＋18px 外边距、操作行 48px＋24px 上外边距，替换帧零跳动 */
  const loading = `<section class="skeleton-result"><div class="skeleton-block skeleton-image"></div><p class="inline-note skeleton-caption">正在演示等待状态，不会调用 AI 或产生费用。</p><div class="skeleton-row"><div class="skeleton-block skeleton-button"></div><div class="skeleton-block skeleton-button"></div></div></section>`;
  const body = state.generationByMode[mode] === "loading" ? loading
    : state.generationByMode[mode] === "error" ? `<section class="empty-state"><h2>这次没有完成</h2><p>失败状态演示。你的描述、选款与本地照片仍在，可以重试。</p>${action("generate", "保留输入，重新尝试", "primary", `data-mode="${mode}"`)}</section>`
      : state.generationByMode[mode] === "ready" ? `<section class="sample-result"><div class="result-image"><img src="${photo(state.resultLooks[mode])}" alt="结果布局示例，既有 AI 图库素材，并非本次生成"></div><span class="image-label">结果布局示例 · 非本次生成</span>${note("这里展示既有样图以便评审布局，尚未根据你的照片或描述生成。")}<div class="action-row">${link(`scheme/${state.resultLooks[mode]}`, "整理成美甲方案", "primary")}${action("save", `${icon("bookmark")}<span class="reaction-label">${state.saved.includes(state.resultLooks[mode]) ? "已收藏" : "收藏示例款"}</span>`, `secondary${state.saved.includes(state.resultLooks[mode]) ? " is-saved" : ""}`, `data-id="${state.resultLooks[mode]}" aria-pressed="${state.saved.includes(state.resultLooks[mode])}" data-label-on="已收藏" data-label-off="收藏示例款"`)}</div></section>`
        : empty("你的新灵感，会出现在这里", "先选一款喜欢的设计，或写下你脑海中的颜色与感觉。", "");
  return `<div class="result-panel" id="result-panel">${body}</div>`;
}
function photoTryon() {
  const slot = state.otherPerson ? "other" : "own";
  const look = byId(state.selectedLook);
  return `${link("tryon", `${icon("back")} 选择其他试戴方式`, "back-link")}${intro("PHOTO TRY-ON", "在你的手上，想象新风格", "AI 上手参考 · 帮你找到搭配灵感。")}<div class="split"><section class="panel"><h2>${state.otherPerson ? "对方这次的手部照片" : "你的手部照片"}</h2>${uploadBox(slot, "选择一张手背清晰、光线均匀的照片")}<p class="inline-note">照片与未提交的草稿仅留在本次浏览器内存；刷新后需重新选择、重新填写。</p><div class="field"><label for="selected-look">这次想试的款</label><select id="selected-look">${looks.map((item) => `<option value="${item.id}" ${item.id === look.id ? "selected" : ""}>${item.original} · ${item.name}</option>`).join("")}</select></div><div class="field"><label for="photo-prompt">还想调整什么？</label><textarea id="photo-prompt" data-draft="photoDraft" maxlength="300" placeholder="比如：保留法式白边，底色更偏奶茶一些…">${esc(state.photoDraft)}</textarea></div>${note("正式版将向选定 AI 服务发送照片与描述；具体服务、费用与处理条款待确认。当前预览不上传。")}<div class="action-row">${action("generate", state.uploads[slot] ? "预览上手结果布局" : "先添加手部照片", "primary", `data-mode="photo" ${state.generationByMode.photo === "loading" ? "disabled" : ""}`)}</div><p class="inline-note">此按钮只演示交互状态，不执行生成。</p></section>${resultPanel("photo")}</div></div>`;
}
function camera() {
  return `${link("tryon", `${icon("back")} 选择其他试戴方式`, "back-link")}${intro("LIVE TRY-ON", "换个颜色，看看此刻的你", "实时摄像头体验将在独立验收后接入。此提案不启动摄像头，也不加载模型。")}<div class="split"><section>${empty("把手轻轻放进画面", "靠近自然光，让手背与五指清晰可见。", action("camera-info", `${icon("camera")} 查看摄像头开启流程`, "primary"))}</section><section class="panel"><h2>先选一种心情</h2><div class="tag-options">${looks.slice(0, 4).map((look) => action("camera-color", look.original, "chip", `data-id="${look.id}" aria-pressed="${state.cameraColor === look.id}"`)).join("")}</div>${note("需覆盖：权限询问、用户拒绝、未找到设备、模型加载、未检测到手和重新尝试。当前只呈现流程，未证明 AR 贴合质量。")}${link("photo", "也可以用照片开始", "secondary")}</section></div>`;
}
function create() {
  return `${intro("YOUR NAIL ATELIER", "让灵感，成为一款美甲", "说说喜欢的颜色与质感。")}<div class="split"><section class="panel"><p class="eyebrow coral">START WITH A FEELING</p><h2>今天，想要怎样的美？</h2><div class="tag-options">${["奶油裸色", "极简法式", "低调微闪", "复古暖调"].map((word) => action("prompt", word, "chip", `data-prompt="${word}"`)).join("")}</div><div class="field"><label for="create-prompt">描述你的灵感</label><textarea id="create-prompt" maxlength="300" data-draft="createDraft" placeholder="比如：适合通勤的奶茶色短甲，加一点细细的金色线条…">${esc(state.createDraft)}</textarea></div><p class="inline-note">未提交的描述草稿仅留在本次浏览器内存；刷新后需重新填写。</p><div class="field"><label>参考图，可选</label>${uploadBox("reference", "添加喜欢的款式或手部照片")}</div>${action("advanced", "画面比例与生成设置", "text-button")}${note("正式生成会发送文字及你主动选择的参考图。当前不连接任何服务，也不产生费用。")}<div class="action-row">${action("generate", `${icon("sparkle")} 预览创作结果布局`, "primary", `data-mode="create" ${state.generationByMode.create === "loading" ? "disabled" : ""}`)}</div></section>${resultPanel("create")}</div></div>`;
}
function detail(id) {
  const look = byId(id);
  state.selectedLook = look.id;
  return `${link("home", `${icon("back")} 回到灵感`, "back-link")}<div class="split"><div class="detail-image"><img src="${photo(look.id)}" alt="${look.original}，AI 生成演示素材"><span class="image-label">AI 设计参考 · 非真实商品</span></div><section><p class="eyebrow coral">THE JIARU EDIT / ${String(look.id).padStart(2, "0")}</p><h1 class="detail-title">${look.name}</h1><p class="detail-summary">${look.description}</p><div class="tag-options" style="margin-top:20px"><span class="chip">${look.tag}</span><span class="chip">${look.scene}</span><span class="chip">${look.original}</span></div><div class="author-row"><a class="avatar" href="#creator" aria-label="查看甲如灵感编辑部主页">J</a><a href="#creator"><strong>甲如灵感编辑部</strong><p>演示账号 · 编辑精选</p></a>${action("follow", `<span class="reaction-label">${state.following ? "已关注" : "+ 关注"}</span>`, `secondary${state.following ? " is-following" : ""}`, `aria-pressed="${state.following}" data-label-on="已关注" data-label-off="+ 关注"`)}</div><p class="inline-note">推荐理由示例：款式标签与你选择的风格相近。真实个性化推荐尚未接入。</p><div class="action-row">${link("tryon", `试戴这一款 ${icon("arrow")}`, "primary")}</div><div class="action-row">${action("save", `${icon("bookmark")}<span class="reaction-label">${state.saved.includes(look.id) ? "已收藏" : "收藏灵感"}</span>`, `secondary${state.saved.includes(look.id) ? " is-saved" : ""}`, `data-id="${look.id}" aria-pressed="${state.saved.includes(look.id)}" data-label-on="已收藏" data-label-off="收藏灵感"`)}${action("like", `${icon("heart")}<span class="reaction-label">${state.liked.includes(look.id) ? "已喜欢" : "喜欢"}</span>`, `secondary${state.liked.includes(look.id) ? " is-liked" : ""}`, `data-id="${look.id}" aria-pressed="${state.liked.includes(look.id)}" data-label-on="已喜欢" data-label-off="喜欢"`)}</div>${link(`scheme/${look.id}`, `整理成方案，给美甲师看看 ${icon("arrow")}`)}${note("点赞、收藏、关注仅保存在独立预览空间；不会影响旧版账号或真实推荐。")}</section></div>`;
}
function saved() {
  const selected = looks.filter((look) => state.saved.includes(look.id));
  return `${intro("YOUR LITTLE COLLECTION", "喜欢，慢慢收藏", "留住这一刻的心动。")}${selected.length ? `<div class="look-grid">${selected.map(lookCard).join("")}</div>` : empty("第一份心动，还在等你", "遇到喜欢的款式，点一下收藏。下一次就能在这里找到。", link("home", "去发现喜欢", "primary"))}`;
}
function profile() {
  return `${intro("A STYLE THAT GROWS WITH YOU", "你的偏好，由你定义", "喜欢与不喜欢，都由你决定。")}<div class="split"><section><div class="preference-card"><p class="eyebrow">MY STYLE NOTES · 偏好描述</p><blockquote>${esc(state.profile || "还没有写下你的偏好。几个关键词，就能开始认识自己喜欢什么。")}</blockquote>${link("onboarding/1", "重新选择偏好", "text-button")}</div><form id="profile-form"><div class="field"><label for="profile-text">直接修改你的描述</label><textarea id="profile-text" data-draft="profileDraft" maxlength="600" placeholder="说说自己喜欢与不喜欢的设计…">${esc(state.profileDraft)}</textarea></div><label class="switch-row"><input type="checkbox" id="learn-toggle" ${state.profileLearnDraft ? "checked" : ""}><span class="switch-knob" aria-hidden="true"></span>允许用后续收藏完善偏好（未来功能，此处只记录选择）</label><button class="primary full-width" type="submit">保存到本地预览</button></form></section><aside class="panel"><h2>让推荐理解你，也听你的</h2><p>收藏与标签是主要线索，手部特点只是较轻的参考。为他人试戴只更换本次照片。</p>${note("此原型的描述来自选项模板，不是语言模型分析。收藏不会在后台悄悄触发任何模型调用。")}${action("cloud-info", "查看跨设备保存方案", "secondary")}</aside></div>`;
}
function me() {
  return `<div class="profile-head"><span class="avatar">J</span><div><h1>${state.loggedIn ? "我的指尖日记" : "你的美甲日记"}</h1><p>${state.loggedIn ? "模拟登录态 · 仅用于评审布局" : "收藏、灵感，还有一点喜欢。"}</p></div></div><div class="stats"><div><strong class="stat-value" data-stat="posts">${state.posts.length}</strong>本地发布预览</div><div><strong class="stat-value" data-stat="saved">${state.saved.length}</strong>收藏灵感</div><div><strong class="stat-value" data-stat="liked">${state.liked.length}</strong>喜欢灵感</div><div><strong class="stat-value" data-stat="following">${state.following ? 1 : 0}</strong>预览关注</div></div><div class="split"><section><div class="preference-card"><p class="eyebrow">MY STYLE NOTES</p><blockquote>${esc(state.profile || "审美没有标准答案，喜欢就是很好的开始。")}</blockquote>${link("profile", `我的偏好描述 ${icon("arrow")}`)}</div>${link("saved", `${icon("bookmark")} 我的收藏 ${icon("arrow")}`, "list-row")}${link("publish", `${icon("upload")} 发布一份新灵感 ${icon("arrow")}`, "list-row")}${link("creator/me", `${icon("user")} 我的公开主页 ${icon("arrow")}`, "list-row")}${action("cloud-info", `${icon("lock")} 本地照片与跨设备保存 ${icon("arrow")}`, "list-row")}${action("login", `${icon("user")} ${state.loggedIn ? "查看模拟账号说明" : "登录后的空间，先体验看看"} ${icon("arrow")}`, "list-row")}</section><aside class="panel"><h2>一些属于自己的空间</h2><p>收藏、灵感、创作与方案，慢慢汇成你的美甲日记。登录后的云端同步将单独建设。</p>${note("原照片默认本地，特点关键词同步云端是已确认的正式版方向。此预览两者都不会上传。")}${link("tryon", "为身边的人试一款", "secondary")}</aside></div>`;
}
function creator(mine) {
  return `${link(mine ? "me" : `look/${state.selectedLook}`, `${icon("back")} 返回`, "back-link")}<div class="profile-head"><span class="avatar">J</span><div><h1>${mine ? "我的灵感小馆" : "甲如灵感编辑部"}</h1><p>${mine ? "公开主页布局预览，尚未实际公开" : "演示账号 · 收集日常里细小而确定的美"}</p></div></div>${mine ? note("这里只呈现你在本次会话提交的发布预览。刷新后不保留上传照片，没有真实公开地址。") : action("follow", `<span class="reaction-label">${state.following ? "已关注" : "+ 关注"}</span>`, `secondary${state.following ? " is-following" : ""}`, `aria-pressed="${state.following}" data-label-on="已关注" data-label-off="+ 关注"`)}<div class="section-heading"><div><p class="eyebrow muted">STYLE JOURNAL</p><h2>${mine ? "发布的灵感" : "编辑精选"}</h2></div></div>${mine ? state.posts.length ? `<div class="look-grid">${state.posts.map((post) => `<article class="look-card"><div class="look-cover"><img src="${post.url}" alt="本地发布预览：${esc(post.title)}"><span class="image-label">仅本地 · 未公开</span></div><h3 class="card-title-row">${esc(post.title)}</h3><p class="card-caption">${esc(post.description)}</p></article>`).join("")}</div>` : empty("让第一份灵感，从这里开始", "分享你的美甲审美与喜欢的款式。正式公开发布与审核尚未接入。", link("publish", "预览发布流程", "primary")) : `<div class="look-grid">${looks.slice(0, 3).map(lookCard).join("")}</div>`}`;
}
function publish() {
  return `${intro("SHARE A LITTLE BEAUTY", "分享一点美", "整理作品 · 仅本地预览")}<div class="split"><form id="publish-form" class="panel">${uploadBox("publish", "上传你想分享的美甲款式")}<div class="field"><label for="publish-title">给这份灵感起个名字</label><input id="publish-title" type="text" maxlength="40" data-draft="publishTitle" value="${esc(state.publishTitle)}" placeholder="比如：我的秋日奶茶法式"></div><div class="field"><label for="publish-text">风格、场景与创作说明</label><textarea id="publish-text" maxlength="300" data-draft="publishDraft" placeholder="说说它让你心动的地方…">${esc(state.publishDraft)}</textarea></div><div class="field"><label for="publish-source">图片来源</label><select id="publish-source">${["本人拍摄或创作", "已获授权转载", "AI 生成设计"].map((source) => `<option ${source === state.publishSource ? "selected" : ""}>${source}</option>`).join("")}</select></div><label class="switch-row"><input type="checkbox" id="publish-rights" ${state.publishRights ? "checked" : ""}><span class="switch-knob" aria-hidden="true"></span>我有权分享这张图片，并愿意在正式发布时公开。</label><p class="inline-note">未提交的标题与说明草稿仅留在本次浏览器内存；刷新后需重新填写。</p><button class="primary full-width" type="submit">${state.loggedIn ? "生成本地发布预览" : "体验登录后，再预览发布"}</button></form><aside class="panel"><h2>分享风格，也尊重创作</h2><p>记录来源，区分实拍与 AI 设计。个人主页、点赞、收藏与关注先行；评论和私信后续再加入。</p>${note("此原型不会把照片上传或公开；公开内容后端、审核机制和真实账号关联均待实施。模拟登录态仅在本次浏览器会话有效，刷新后需重新进入。")}</aside></div>`;
}
function scheme(id) {
  const look = byId(id);
  return `${intro("YOUR NAIL NOTE", "把喜欢，带给美甲师", "一张卡，装下款式与想法。")}<div class="split"><article class="scheme-card" id="scheme-card"><div class="scheme-top"><span class="wordmark">JiaRu</span><span class="eyebrow muted">MY NAIL NOTE</span></div><div class="scheme-photo"><img src="${photo(look.id)}" alt="${look.original}的款式参考，AI 演示素材"></div><h2>${look.name}</h2><p>${look.description}</p><dl><dt>风格参考</dt><dd>${look.original} / ${look.tag}</dd><dt>长度偏好</dt><dd>${esc(state.length)}</dd><dt>使用场景</dt><dd>${esc(state.scenes.join("、") || look.scene)}</dd><dt>补充需求</dt><dd>${esc((state.schemeOrigin === "create" ? state.createDraft : state.photoDraft) || "结合实际甲面与美甲师建议调整。")}</dd></dl><div class="signature">AI 灵感参考 · 非实际制作效果 · JIARU</div></article><aside class="panel"><h2>一份灵感，一次更好的沟通</h2><p>当前卡片使用已选的演示款式，并不包含你手部照片的生成结果。正式制作前，请与美甲师确认材料、长度与可实现效果。</p><div class="action-row">${action("share-scheme", `${icon("share")} 分享方案`, "primary", `data-id="${look.id}" disabled aria-busy="true"`)}</div><div class="action-row">${action("download-scheme", `${icon("photo")} 保存图片`, "secondary", `data-id="${look.id}"`)}</div><div class="action-row">${action("copy-scheme", "复制方案文字", "secondary", `data-id="${look.id}"`)}</div>${link(state.schemeOrigin, `${icon("back")} 返回继续调整`, "text-button", "data-return-editor")}</aside></div>`;
}
function tagOption(value, group, checked, radio = false) {
  return `<label class="tag-option"><input type="${radio ? "radio" : "checkbox"}" name="${group}" value="${value}" ${checked ? "checked" : ""}><span>${checkIcon}${value}</span></label>`;
}
function onboarding(step) {
  const stage = Math.max(1, Math.min(4, Number(step) || 1));
  let content;
  if (stage === 1) content = `<p class="step-number">01.</p><h1 class="step-title">哪些感觉，让你心动？</h1><p class="step-description">不用急着给风格下定义。先选几个喜欢的词，也可以不选。</p><fieldset class="tag-options"><legend class="skip-link">喜欢的风格，可多选</legend>${["自然", "简约", "轻闪", "复古", "温柔", "个性"].map((word) => tagOption(word, "styles", state.styles.includes(word))).join("")}</fieldset><div class="field"><label for="onboarding-note">用自己的话补充一点</label><textarea id="onboarding-note" data-draft="preferenceNote" maxlength="300" placeholder="比如：低饱和、不夸张，但希望有一点细节…">${esc(state.preferenceNote)}</textarea></div>`;
  if (stage === 2) content = `<p class="step-number">02.</p><h1 class="step-title">美，也要适合你的日常。</h1><p class="step-description">长期喜好与这次需求可以不同，以后都能调整。</p><fieldset class="field"><legend>主要使用场景，可多选</legend><div class="tag-options">${["日常", "通勤", "约会", "出游", "聚会", "婚礼"].map((word) => tagOption(word, "scenes", state.scenes.includes(word))).join("")}</div></fieldset><fieldset class="field"><legend>平时更舒服的长度</legend><div class="tag-options">${["短甲", "中长甲", "长甲"].map((word) => tagOption(word, "length", state.length === word, true)).join("")}</div></fieldset>`;
  if (stage === 3) content = `<p class="step-number">03.</p><h1 class="step-title">也可以，认识你的手。</h1><p class="step-description">加一张手背照片，也可以跳过。</p><div class="field">${uploadBox("own", "添加一张清晰手背照片，可跳过")}</div>${note("正式版可将照片交给视觉模型提取特点，原照片默认本地保存，特点关键词同步云端。此预览不分析、不上传，也不把照片写入本地持久存储。")}`;
  if (stage === 4) content = `<p class="step-number">04.</p><h1 class="step-title">这份描述，像你吗？</h1><p class="step-description">描述应帮助你表达喜好，而不是限制你的选择。</p><div class="field"><label for="onboarding-summary">偏好描述，可直接修改</label><textarea id="onboarding-summary" data-draft="onboardingSummaryDraft" maxlength="600">${esc(state.onboardingSummaryDraft ?? (state.profile?.trim() ? state.profile : preferenceText()))}</textarea><small>${state.profile?.trim() ? "已保存的描述 · 可修改" : "选项模板 · 可修改"}</small></div><label class="switch-row"><input type="checkbox" id="onboarding-learn" ${state.onboardingLearnDraft ? "checked" : ""}><span class="switch-knob" aria-hidden="true"></span>逐渐了解我的偏好（未来功能）</label>`;
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
  const routeTitles = { home: "为你", tryon: "试戴", photo: "照片试戴", camera: "摄像头试戴", create: "创作", me: "我的", profile: "我的偏好", saved: "我的收藏", publish: "发布灵感", onboarding: "了解你的偏好", scheme: "我的美甲方案", creator: parameter === "me" ? "我的灵感小馆" : "灵感主页", look: byId(parameter).name };
  document.title = `${routeTitles[currentRoute] ?? "灵感空间"} · 甲如设计提案`;
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
  upgradeStats();
  updateViewport();
  if (currentRoute === "scheme") prepareScheme(parameter);
}
function showLogin(then) {
  modal("先体验登录后的空间", `<p>这是独立设计提案，不连接真实登录服务。继续后只切换本地模拟状态，不代表账号已认证，也不会开启云同步。</p><p>模拟登录态仅在本次浏览器会话有效，刷新后需重新进入。</p><div class="action-row">${action("simulate-login", "进入模拟登录态", "primary", then ? `data-then="${then}"` : "")}</div>`);
}
function toggle(list, id) {
  const had = state[list].includes(id);
  state[list] = had ? state[list].filter((value) => value !== id) : [...state[list], id];
  const persisted = persist({ quiet: true });
  return { active: !had, persisted };
}
/* ===== 喜欢/收藏统一交互（2026-10-23）=====
   目标：点击后不重渲染页面或区块，只就地更新被点的图标钮/文字钮与可见计数。
   反馈：持久选中态（珊瑚填充＋实心图标）＋340ms 回弹脉冲＋轻档爆散＋明确文案提示；
   失败（本地存储不可用）回滚界面并给出失败提示；快速连点、取消再点均以内存状态为准。 */
const reactionCopy = {
  save: { on: "已收藏", off: "收藏灵感", onVerb: "取消收藏", offVerb: "收藏", done: "已收藏", undone: "已取消收藏", failed: "收藏未保存" },
  like: { on: "已喜欢", off: "喜欢", onVerb: "取消喜欢", offVerb: "喜欢", done: "已喜欢", undone: "已取消喜欢", failed: "喜欢未保存" },
  follow: { on: "已关注", off: "+ 关注", onVerb: "取消关注", offVerb: "关注", done: "已关注", undone: "已取消关注", failed: "关注未保存" },
};
const reactionClass = (kind) => (kind === "save" ? "is-saved" : kind === "like" ? "is-liked" : "is-following");
const followButtons = () => [...document.querySelectorAll('[data-action="follow"]')];
function reactionButtons(kind, id) {
  return [...document.querySelectorAll(`[data-action="${kind}"][data-id="${CSS.escape(String(id))}"]`)];
}
function paintReaction(button, kind, active, name) {
  const copy = reactionCopy[kind];
  button.setAttribute("aria-pressed", String(active));
  button.classList.toggle(reactionClass(kind), active);
  const label = button.querySelector(".reaction-label");
  if (label) label.textContent = active ? (button.dataset.labelOn ?? copy.on) : (button.dataset.labelOff ?? copy.off);
  /* 文字按钮的可访问名即可见文字（保持一致）；纯图标钮才用 aria-label 补名称 */
  if (name && !label) button.setAttribute("aria-label", `${active ? copy.onVerb : copy.offVerb}${name}`);
}
function currentScale(element) {
  const value = getComputedStyle(element).transform;
  return value && value !== "none" ? Number(value.slice(7, -1).split(",")[0]) : 1;
}
function pulseReaction(button) {
  if (reducedMotion.matches || !button?.animate) return;
  button.getAnimations().forEach((animation) => {
    /* 连点时重启脉冲而非叠加；释放回弹让位给脉冲，避免两条 transform 动画抢同一属性 */
    if (animation.id === "reaction-pulse" || animation.id === "press-rebound") animation.cancel();
  });
  button.animate([
    { transform: `scale(${currentScale(button)})`, offset: 0 },
    { transform: "scale(1.09)", offset: .42 },
    { transform: "scale(.985)", offset: .74 },
    { transform: "scale(1)" },
  ], { duration: 340, easing: "cubic-bezier(.34,1.56,.64,1)" }).id = "reaction-pulse";
}
/* 读回统计位当前显示值（数字列按 translateY(-1.2em/位) 还原） */
function displayedStatValue(node) {
  const columns = [...node.querySelectorAll(".digit-column")];
  if (!columns.length) return node.textContent.trim();
  return columns.map((column) => {
    const match = column.style.transform.match(/translateY\((-?[\d.]+)em\)/);
    return String(Math.round(-Number(match?.[1] ?? 0) / 1.2));
  }).join("");
}
/* 若当前页同时展示了统计数字（我的页），就地滚动更新，不重建整块统计区 */
function syncStatCounter(key, next) {
  document.querySelectorAll(`.stats .stat-value[data-stat="${key}"]`).forEach((node) => {
    const target = String(next);
    const previous = statPrevious.get(key) ?? displayedStatValue(node);
    if (previous === target) { statPrevious.set(key, target); return; }
    statPrevious.set(key, target);
    if (!reducedMotion.matches && node.animate) rollNumber(node, previous, target);
    else node.textContent = target;
  });
}
/* 局部重置结果面板（换款、重新上传等）：只替换面板节点并复位按钮，不动页面其他区域 */
function resetResultPanel(mode) {
  const host = $("#result-panel");
  if (!host) return;
  const template = document.createElement("div");
  template.innerHTML = resultPanel(mode);
  host.replaceWith(template.firstElementChild);
  const generate = $(`[data-action="generate"][data-mode="${mode}"]`);
  if (!generate) return;
  generate.removeAttribute("disabled");
  generate.removeAttribute("aria-busy");
  if (mode === "photo") generate.textContent = state.uploads[state.otherPerson ? "other" : "own"] ? "预览上手结果布局" : "先添加手部照片";
}
/* 上传回执只替换对应上传位与按钮文案：不重建页面，图片、表单与其他区块保持原节点 */
function patchUploadAfterAccept(slot, mode, wasGenerating) {
  const input = document.querySelector(`input[data-upload="${CSS.escape(slot)}"]`);
  const box = input?.closest(".upload-box");
  if (box) {
    const label = box.querySelector("span")?.textContent ?? "";
    const template = document.createElement("div");
    template.innerHTML = uploadBox(slot, label);
    box.replaceWith(template.firstElementChild);
  }
  if (!mode) return;
  const generate = $(`[data-action="generate"][data-mode="${mode}"]`);
  if (generate) {
    generate.removeAttribute("disabled");
    generate.removeAttribute("aria-busy");
    if (mode === "photo") generate.textContent = "预览上手结果布局";
  }
  if (wasGenerating) resetResultPanel(mode);
  if (slot === "own") {
    const submit = $("#onboarding-form[data-step='3'] button[type='submit']");
    if (submit) submit.innerHTML = `继续 ${icon("arrow")}`;
  }
}
/* 收藏页取消收藏：只收起该卡，必要时把列表换成空态，避免整页重建 */
function pruneSavedCard(id) {
  if (currentRoute !== "saved") return;
  const card = document.querySelector(`#main .look-grid .look-card:has([data-action="save"][data-id="${CSS.escape(String(id))}"])`);
  if (!card) return;
  const finish = () => {
    card.remove();
    const grid = document.querySelector("#main .look-grid");
    if (!grid || grid.querySelector(".look-card")) return;
    const host = grid.parentElement;
    grid.remove();
    host?.insertAdjacentHTML("beforeend", empty("第一份心动，还在等你", "遇到喜欢的款式，点一下收藏。下一次就能在这里找到。", link("home", "去发现喜欢", "primary")));
  };
  if (reducedMotion.matches || !card.animate) { finish(); return; }
  const animation = card.animate([
    { opacity: 1, transform: "scale(1)" },
    { opacity: 0, transform: "scale(.97)" },
  ], { duration: 220, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" });
  animation.onfinish = finish;
  animation.oncancel = finish;
}
function simulateGeneration(mode) {
  if (mode === "photo" && !state.uploads[state.otherPerson ? "other" : "own"]) { toast("请先添加本次手部照片。照片仅在本地预览。"); return; }
  if (mode === "create" && !state.createDraft.trim()) { toast("先写一点喜欢的颜色或感觉，也可以点选灵感词。"); return; }
  clearTimeout(jobTimers[mode]);
  state.generationByMode[mode] = "loading";
  state.resultLooks[mode] = state.selectedLook;
  focusAfterRoute = false;
  /* 生成开始只切换结果面板与生成按钮：表单、草稿文本与滚动位置保持原节点 */
  const panel = $("#result-panel");
  if (panel) {
    const template = document.createElement("div");
    template.innerHTML = resultPanel(mode);
    panel.replaceWith(template.firstElementChild);
  }
  const startButton = $(`[data-action="generate"][data-mode="${mode}"]`);
  startButton?.setAttribute("disabled", "");
  startButton?.setAttribute("aria-busy", "true");
  jobTimers[mode] = setTimeout(() => {
    state.generationByMode[mode] = "ready";
    if (currentRoute !== mode) return;
    const generateButton = $(`[data-action="generate"][data-mode="${mode}"]`);
    generateButton?.removeAttribute("disabled");
    generateButton?.removeAttribute("aria-busy");
    const host = $("#result-panel");
    if (!host?.querySelector(".skeleton-result")) { render(); return; }
    /* 骨架→内容交叉淡入淡出（§2.8）：两态同格堆叠，骨架 180ms 淡出后移除，替换帧零跳动 */
    const ready = document.createElement("div");
    ready.innerHTML = resultPanel(mode);
    host.classList.add("is-swapping");
    host.append(ready.firstElementChild.firstElementChild);
    const skeleton = host.querySelector(".skeleton-result");
    const cleanup = () => { skeleton.remove(); host.classList.remove("is-swapping"); };
    skeleton.classList.add("is-leaving");
    skeleton.addEventListener("transitionend", cleanup, { once: true });
    setTimeout(cleanup, 400);
    burst(generateButton, "medium");
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
async function acceptFile(slot, file, input = null) {
  const sequence = (uploadSequence[slot] ?? 0) + 1; uploadSequence[slot] = sequence;
  try {
    await validateUpload(file);
    if (uploadSequence[slot] !== sequence) return;
    if (state.uploads[slot]) URL.revokeObjectURL(state.uploads[slot].url);
    state.uploads[slot] = { name: file.name, url: URL.createObjectURL(file) };
    const mode = slot === "reference" ? "create" : ["own", "other"].includes(slot) ? "photo" : null;
    const wasGenerating = Boolean(mode) && state.generationByMode[mode] !== "idle";
    if (mode) { clearTimeout(jobTimers[mode]); state.generationByMode[mode] = "idle"; }
    /* 只换上传位与相关按钮文案，不重建页面：避免选完照片后整页重绘、详情折叠面板被复位 */
    focusAfterRoute = false;
    patchUploadAfterAccept(slot, mode, wasGenerating);
    toast("照片仅已加入本次本地预览，没有上传。");
  } catch (error) { if (input) input.value = ""; toast(error instanceof Error ? error.message : "图片解码失败，请更换照片。"); }
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
  ctx.fillStyle = "#292a27"; ctx.font = 'italic 52px "Segoe Script", "Snell Roundhand", "Brush Script MT", "Iowan Old Style", serif'; ctx.fillText("JiaRu", 70, 100);
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
      if (ctx.measureText(current + char).width > 850) { if (y > 1410) { ctx.fillText(`${current.slice(0, -1)}…`, 70, y); break; } ctx.fillText(current, 70, y); y += 38; current = ""; }
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
async function downloadScheme(id, control) { saveSchemeFile(await prepareScheme(id).promise); burst(control, "medium"); }
async function shareScheme(id, control) {
  const record = prepareScheme(id);
  if (!record.file) { toast("方案图片正在准备，请稍后再试。"); return; }
  if (typeof navigator.share !== "function" || !navigator.canShare?.({ files: [record.file] })) { saveSchemeFile(record.file); burst(control, "medium"); return; }
  try { await navigator.share({ files: [record.file], title: "我的美甲方案", text: "甲如 · AI 灵感参考，非实际制作效果" }); toast("已交给系统分享面板。"); burst(control, "medium"); }
  catch (error) { if (error.name !== "AbortError") { saveSchemeFile(record.file); burst(control, "medium"); } }
}
function updateViewport() {
  const viewport = window.visualViewport;
  const field = document.activeElement;
  const editing = field?.matches?.('textarea:not([readonly]), input:not([readonly]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=button]):not([type=submit])');
  const inset = viewport ? Math.max(0, innerHeight - viewport.height - viewport.offsetTop) : 0;
  const keyboard = Boolean(viewport && editing && Math.abs(viewport.scale - 1) < .02 && inset > Math.max(120, innerHeight * .18));
  document.body.classList.toggle("keyboard-open", keyboard);
  document.documentElement.style.setProperty("--keyboard-inset", keyboard ? `${inset}px` : "0px");
  document.querySelectorAll(".filters-wrap").forEach((wrap) => {
    const list = wrap.firstElementChild;
    if (list) wrap.classList.toggle("is-overflowing", list.scrollWidth > list.clientWidth + 1);
  });
}
let modalExit;
function closeModal() {
  const dialog = $("#sheet");
  if (!dialog.open) return;
  const exit = motion(dialog, [{ opacity: 1, transform: "translateY(0) scale(1)" }, { opacity: 0, transform: "translateY(10px) scale(.98)" }], { duration: 170, easing: "cubic-bezier(.4,0,1,1)" });
  if (!exit) { dialog.close(); return; }
  modalExit = exit;
  const finish = () => { const closing = modalExit === exit; modalExit = null; if (closing) dialog.close(); };
  exit.onfinish = finish;
  exit.oncancel = finish;
}
function updateSearch() {
  const results = $("#look-results");
  if (!results) return;
  results.innerHTML = lookResults(); revealCards();
}
/* ===== 动效演示弹层（方案第三批：汉堡/液态滑杆/翻面/堆叠的演示宿主）===== */
function motionDemoBody() {
  return `<div class="motion-demo">
<section><h3>汉堡图标变换</h3><p class="demo-hint">同一组线条连续形变：中线先收，上下线晚 40ms 旋转成 X；按钮自身不移动，位置不丢失。</p>
<div style="display:flex;gap:16px;align-items:center;margin-top:12px"><button type="button" class="morph-toggle" aria-expanded="false" aria-controls="morph-panel" aria-label="打开演示菜单"><span class="morph-line"></span><span class="morph-line"></span><span class="morph-line"></span></button><div class="morph-panel" id="morph-panel" hidden><span class="morph-item">演示菜单 · 为你</span><span class="morph-item">演示菜单 · 试戴</span><span class="morph-item">演示菜单 · 我的</span></div></div></section>
<section><h3>液态滑杆</h3><p class="demo-hint">轨道填充、滑钮与液面隆起由同一条时间轴驱动（400ms 同曲线）；松手吸附 5 档并过冲回弹；支持拖动与方向键。</p>
<div class="liquid-slider" data-demo="slider" style="margin-top:14px"><div class="liquid-track"><div class="liquid-fill"></div><div class="liquid-bulge"></div><div class="liquid-knob" role="slider" tabindex="0" aria-valuemin="0" aria-valuemax="100" aria-valuenow="40" aria-label="演示强度"></div></div>
<div class="liquid-ticks" aria-hidden="true"><i style="left:calc(.25 * (100% - 24px) + 11px)"></i><i style="left:calc(.5 * (100% - 24px) + 11px)"></i><i style="left:calc(.75 * (100% - 24px) + 11px)"></i></div>
<span class="liquid-value">强度 <span class="stat-value" data-stat="liquid">40</span>%</span></div></section>
<section><h3>卡片翻面</h3><p class="demo-hint">正面与反面各自隐藏背面（backface-visibility），翻转中途不穿帮；可中断反向。</p>
<div class="flip-card" data-demo="flip" style="margin-top:12px"><div class="flip-inner"><div class="flip-face front"><span class="face-tag">FRONT · 款式</span><h4>渐变裸粉</h4><p class="demo-hint">柔和裸粉与细腻渐层。正面只放最想让人先看见的信息。</p></div><div class="flip-face back"><span class="face-tag">BACK · 工艺</span><h4>工艺与配色</h4><p class="demo-hint">背面放参数与说明。两面各自隐藏背面，任何角度不穿帮。</p></div></div></div>
<div class="stack-actions">${action("flip-demo", "翻面", "secondary")}</div></section>
<section><h3>卡片抽走与堆叠</h3><p class="demo-hint">抽走最上面的卡片时，后方卡片同帧跟进，堆叠关系始终可见；未过阈值则弹回。可拖动，也可点按钮。</p>
<div class="stack-demo" data-demo="stack" style="margin-top:12px">${[0, 1, 2].map((depth) => `<article class="stack-card${depth === 0 ? " is-top" : ""}" data-depth="${depth}" style="--depth:${depth}"><h4>堆叠卡片 ${3 - depth}</h4><p>第 ${3 - depth} 层${depth === 0 ? "，可拖动或抽走" : "，随前卡移动显露"}。</p></article>`).join("")}</div>
<div class="stack-actions">${action("stack-remove", "抽走最上面", "secondary")}${action("stack-undo", "放回最上面", "secondary")}</div></section>
<p class="demo-note">以上为动效演示宿主，用于评审 11 项交互细节的参数与手感；不接入真实数据，也不代表最终产品结构。</p></div>`;
}
function openMotionDemo() { statPrevious.delete("liquid"); modal("动效演示", motionDemoBody()); wireMotionDemo(); }
function wireMotionDemo() {
  const sheet = $("#sheet");
  /* 汉堡形变：aria-expanded 驱动线条旋转，面板显隐同步 */
  const morph = sheet.querySelector(".morph-toggle");
  const panel = sheet.querySelector(".morph-panel");
  morph?.addEventListener("click", () => {
    const expanded = morph.getAttribute("aria-expanded") === "true";
    morph.setAttribute("aria-expanded", String(!expanded));
    morph.setAttribute("aria-label", expanded ? "打开演示菜单" : "关闭演示菜单");
    panel.hidden = expanded;
  });
  /* 卡片翻面 */
  sheet.querySelector('[data-action="flip-demo"]')?.addEventListener("click", () => {
    sheet.querySelector(".flip-card")?.classList.toggle("is-flipped");
  });
  wireLiquidSlider(sheet.querySelector(".liquid-slider"));
  wireStackDemo(sheet.querySelector(".stack-demo"));
}
function wireLiquidSlider(slider) {
  if (!slider) return;
  const track = slider.querySelector(".liquid-track");
  const knob = slider.querySelector(".liquid-knob");
  const output = slider.querySelector(".liquid-value .stat-value");
  const detents = [0, .25, .5, .75, 1];
  let bulgeTimer;
  let dragging = false;
  const pulseBulge = () => {
    if (reducedMotion.matches) return;
    slider.classList.add("is-adjusting");
    clearTimeout(bulgeTimer);
    bulgeTimer = setTimeout(() => slider.classList.remove("is-adjusting"), 400);
  };
  const applyValue = (value, { snap = true, roll = true } = {}) => {
    const target = snap ? detents.reduce((best, candidate) => (Math.abs(candidate - value) < Math.abs(best - value) ? candidate : best), detents[0]) : value;
    slider.style.setProperty("--v", String(target));
    const percent = String(Math.round(target * 100));
    knob.setAttribute("aria-valuenow", percent);
    const previous = statPrevious.get("liquid");
    statPrevious.set("liquid", percent);
    if (roll && previous !== undefined && previous !== percent) rollNumber(output, previous, percent);
    else if (!output.querySelector(".digit")) output.textContent = percent;
    pulseBulge();
  };
  const valueFromClientX = (clientX) => {
    const rect = track.getBoundingClientRect();
    const usable = Math.max(1, rect.width - 24);
    return Math.min(1, Math.max(0, (clientX - rect.left - 12) / usable));
  };
  knob.addEventListener("pointerdown", (event) => {
    dragging = true;
    slider.classList.add("is-dragging");
    knob.setPointerCapture(event.pointerId);
    pulseBulge();
    event.preventDefault();
  });
  knob.addEventListener("pointermove", (event) => { if (dragging) applyValue(valueFromClientX(event.clientX), { snap: false, roll: false }); });
  const endDrag = (event) => {
    if (!dragging) return;
    dragging = false;
    slider.classList.remove("is-dragging");
    applyValue(valueFromClientX(event.clientX));
  };
  knob.addEventListener("pointerup", endDrag);
  knob.addEventListener("pointercancel", endDrag);
  track.addEventListener("pointerdown", (event) => {
    if (event.target === knob || knob.contains(event.target)) return;
    applyValue(valueFromClientX(event.clientX));
  });
  knob.addEventListener("keydown", (event) => {
    const current = Number(knob.getAttribute("aria-valuenow")) / 100;
    const step = event.shiftKey ? .5 : .25;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") { applyValue(Math.min(1, current + step)); event.preventDefault(); }
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown") { applyValue(Math.max(0, current - step)); event.preventDefault(); }
    else if (event.key === "Home") { applyValue(0); event.preventDefault(); }
    else if (event.key === "End") { applyValue(1); event.preventDefault(); }
  });
}
function wireStackDemo(stack) {
  if (!stack) return;
  const undo = $("#sheet [data-action=\"stack-undo\"]");
  const cards = () => [...stack.querySelectorAll(".stack-card")];
  let removed = null;
  /* flying=抽走动画进行中；removed=已抽走、可被「放回最上面」恢复的那张卡。
     两者必须分开：动画结束后卡片已移出 DOM，但只要用户没有撤销，它仍应可恢复。 */
  let flying = false;
  const reindex = (skip) => {
    let depth = 0;
    cards().forEach((card) => {
      if (card === skip) return;
      card.style.setProperty("--depth", String(depth));
      card.dataset.depth = String(depth);
      card.classList.toggle("is-top", depth === 0);
      depth += 1;
    });
    if (undo) undo.hidden = cards().length >= 3;
  };
  const flyOut = (card, direction) => {
    if (flying) return;
    flying = true;
    removed = card;
    const rect = card.getBoundingClientRect();
    const distance = direction * (rect.width * .8 + 80);
    card.classList.remove("is-dragging");
    card.style.transform = "";
    reindex(card);
    if (undo) undo.hidden = false;
    if (reducedMotion.matches) { card.remove(); flying = false; return; }
    const animation = card.animate([
      { transform: "translateX(-50%) translateY(0) scale(1)", opacity: 1 },
      { transform: `translateX(calc(-50% + ${distance * .7}px)) translateY(-10px) rotate(${direction * 5}deg)`, opacity: .95, offset: .65 },
      { transform: `translateX(calc(-50% + ${distance}px)) translateY(6px) rotate(${direction * 8}deg)`, opacity: 0 },
    ], { duration: 340, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" });
    const settle = () => { card.remove(); flying = false; };
    animation.onfinish = settle;
    animation.oncancel = settle;
  };
  stack.addEventListener("pointerdown", (event) => {
    const card = event.target.closest(".stack-card");
    if (!card || !card.classList.contains("is-top") || flying) return;
    const startX = event.clientX;
    const startY = event.clientY;
    card.classList.add("is-dragging");
    try { card.setPointerCapture(event.pointerId); } catch { /* 指针捕获失败时退化为文档级跟随 */ }
    const move = (moveEvent) => {
      const dx = moveEvent.clientX - startX;
      const dy = moveEvent.clientY - startY;
      const tilt = Math.max(-4, Math.min(4, dx / 40));
      card.style.transform = `translateX(calc(-50% + ${dx}px)) translateY(${dy}px) rotate(${tilt}deg)`;
    };
    const finish = (finishEvent) => {
      card.removeEventListener("pointermove", move);
      card.classList.remove("is-dragging");
      const dx = finishEvent.clientX - startX;
      const dy = finishEvent.clientY - startY;
      const rect = card.getBoundingClientRect();
      const threshold = Math.min(96, rect.width * .4);
      card.style.transform = "";
      if (Math.abs(dx) >= threshold) { flyOut(card, dx >= 0 ? 1 : -1); return; }
      if (reducedMotion.matches) return;
      const tilt = Math.max(-4, Math.min(4, dx / 40));
      card.animate([
        { transform: `translateX(calc(-50% + ${dx}px)) translateY(${dy}px) rotate(${tilt}deg)` },
        { transform: "translateX(-50%) translateY(0) rotate(0deg)" },
      ], { duration: 340, easing: "cubic-bezier(.34,1.56,.64,1)" });
    };
    card.addEventListener("pointermove", move);
    card.addEventListener("pointerup", finish);
    card.addEventListener("pointercancel", finish);
    event.preventDefault();
  });
  $("#sheet [data-action=\"stack-remove\"]")?.addEventListener("click", () => {
    const top = cards()[0];
    if (top && !flying) flyOut(top, 1);
  });
  undo?.addEventListener("click", () => {
    if (!removed || flying) return;
    const card = removed;
    removed = null;
    card.classList.add("is-top");
    stack.prepend(card);
    reindex();
    if (!reducedMotion.matches) {
      card.animate([
        { transform: "translateX(calc(-50% + 90px)) translateY(-6px) scale(.96)", opacity: 0 },
        { transform: "translateX(-50%) translateY(0) scale(1)", opacity: 1 },
      ], { duration: 320, easing: "cubic-bezier(.4,0,.2,1)" });
    }
    undo.hidden = true;
  });
  reindex();
}

document.addEventListener("click", async (event) => {
  const anchor = event.target.closest("a[href^='#']");
  if (anchor && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
    event.preventDefault();
    if (anchor.classList.contains("skip-link")) { $("#main").focus({ preventScroll: true }); return; }
    closeModal();
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
      /* 只改内存状态与就地界面：不 render()、不重设滚动，图片与页面节点保持不动 */
      const look = byId(button.dataset.id);
      const list = name === "save" ? "saved" : "liked";
      const { active, persisted } = toggle(list, look.id);
      if (!persisted) {
        state[list] = active ? state[list].filter((value) => value !== look.id) : [...state[list], look.id];
        reactionButtons(name, look.id).forEach((node) => paintReaction(node, name, !active, look.name));
        toast(`${reactionCopy[name].failed}：本地预览存储不可用，本次改动已回滚。`);
        return;
      }
      reactionButtons(name, look.id).forEach((node) => paintReaction(node, name, active, look.name));
      pulseReaction(button);
      syncStatCounter(list, state[list].length);
      if (name === "save" && !active) pruneSavedCard(look.id);
      /* 轻档爆散：原点跟随指针（键盘触发取控件中心），与回弹脉冲叠加 */
      burst(button, "light", event.detail ? { x: event.clientX, y: event.clientY } : null);
      toast(active ? `${reactionCopy[name].done}「${look.name}」` : `${reactionCopy[name].undone}「${look.name}」`);
    }
    if (name === "follow") {
      if (!state.loggedIn) { showLogin("follow"); }
      else {
        /* 与喜欢/收藏同一套就地更新：只改关注按钮与可见计数，不重建页面其他区域 */
        const next = !state.following;
        state.following = next;
        const persisted = persist({ quiet: true });
        if (!persisted) {
          state.following = !next;
          followButtons().forEach((node) => paintReaction(node, "follow", !next));
          toast("关注未保存：本地预览存储不可用，本次改动已回滚。");
          return;
        }
        followButtons().forEach((node) => paintReaction(node, "follow", next));
        pulseReaction(button);
        syncStatCounter("following", next ? 1 : 0);
        burst(button, "light", event.detail ? { x: event.clientX, y: event.clientY } : null);
        toast(next ? "已关注「甲如灵感编辑部」" : "已取消关注「甲如灵感编辑部」");
      }
    }
    if (name === "simulate-login") {
      state.loggedIn = true;
      const followNext = button.dataset.then === "follow";
      if (followNext) { state.following = true; persist(); }
      /* 弹层位于浏览器顶层，爆散层会被遮挡：先取坐标，关闭并渲染后再爆 */
      const rect = button.getBoundingClientRect();
      const point = rect.width > 0 ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } : null;
      $("#sheet").close(); render();
      if (!followNext && point) burstAt(point.x, point.y, "light");
      if (followNext) burst($('[data-action="follow"]'), "light");
      toast("已进入模拟登录态，尚无云同步。");
    }
    if (name === "login") showLogin();
    if (name === "filter") {
      /* 标签切换只重排结果网格与自身选中态；页头、搜索框、筛选条与滚动位置保持不动 */
      if (state.filter === button.dataset.filter) return;
      state.filter = button.dataset.filter;
      document.querySelectorAll('.filters [data-action="filter"]').forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.filter === state.filter)));
      updateSearch();
    }
    if (name === "prompt") {
      /* 灵感词只把文字补进描述框，不重渲染（重渲染会重建 textarea 并丢失光标） */
      state.createDraft = state.createDraft ? `${state.createDraft}，${button.dataset.prompt}`.slice(0, 300) : button.dataset.prompt;
      const field = $("#create-prompt");
      if (field) { field.value = state.createDraft; field.dispatchEvent(new Event("input", { bubbles: true })); }
    }
    if (name === "generate") simulateGeneration(button.dataset.mode);
    if (name === "skip-onboarding") { state.onboarded = true; persist(); navigate("home"); toast("可以先随意逛逛，之后在“我的”补充偏好。"); }
    if (name === "cloud-info") modal("你的照片，与你的偏好", "<p>已确认的正式版方向：手部原照片默认本地；特点关键词、偏好和作品支持登录后跨设备。为他人使用不覆盖主人手部档案。</p><p>此提案没有云端接口。文字与收藏只写入独立本地预览空间；上传图片仅存内存，关闭或刷新页面后需重新选择。</p>");
    if (name === "camera-info") modal("摄像头流程提案", "<p>正式版流程：主动点击开启 → 浏览器询问权限 → 加载识别资源 → 放入手背 → 选择颜色或纹理。</p><p>权限被拒绝时，说明如何重新授权，并始终提供照片入口。当前提案不申请权限，也未启动摄像头。</p>");
    if (name === "camera-color") {
      /* 预选色只切换标签选中态，不重建页面 */
      state.cameraColor = byId(button.dataset.id).id;
      document.querySelectorAll('[data-action="camera-color"]').forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.id === String(state.cameraColor))));
      toast(`已预选${byId(button.dataset.id).original}，开启摄像头后生效。`);
    }
    if (name === "advanced") modal("生成设置的位置", "<p>普通用户先表达想法。画面比例、尺寸与引擎放入次级设置，保留默认值，并说明不同服务的费用和等待时间。</p><p>当前未选择模型服务，此提案不展示未经实测的价格或速度承诺。</p>");
    if (name === "show-notes") modal("这是一份可交互设计提案", "<p>已经可体验：页面导航、轻问答、偏好模板与纠正、本地收藏、上传预览、模拟登录后的发布布局、方案卡下载、动效演示（按压回弹、水波、爆散、逐笔勾选、数字滚动、骨架屏、汉堡形变、液态滑杆、卡片翻面与堆叠抽走）。</p><p>尚未接入：语言模型、真实生成、自动推荐、跨设备同步、真实登录、公开发布与关注、摄像头和 AR。全部图片为既有 AI 演示素材。</p><p>旧版页面、账户数据库和模型发布状态保持原状。</p>");
    if (name === "show-error") { clearTimeout(jobTimers.create); state.generationByMode.create = "error"; if (currentRoute === "create") render(); else navigate("create"); }
    if (name === "empty") modal("还没有内容，也不必着急", `<p>收藏为空时应说明下一步，发布为空时应邀请创作，而不是用假数据填充。</p>${empty("第一份心动，还在等你", "去发现喜欢，或开始一份新的创作。", link("home", "去发现", "primary"))}`);
    if (name === "wireframe") document.body.classList.toggle("wireframe");
    if (name === "motion-demo") openMotionDemo();
    if (name === "reset") modal("重置这份预览？", `<p>仅删除此提案的偏好和收藏，清空本次图片与草稿。旧版数据不受影响。</p><div class="action-row">${action("confirm-reset", "重置本地预览", "primary")}</div>`);
    if (name === "confirm-reset") { localStorage.removeItem(storageKey); releaseUploads(); location.hash = "home"; location.reload(); }
    if (name === "download-scheme") await downloadScheme(button.dataset.id, button);
    if (name === "share-scheme") await shareScheme(button.dataset.id, button);
    if (name === "copy-scheme") {
      const look = byId(button.dataset.id);
      const text = `甲如美甲方案\n${look.name} / ${look.original}\n长度：${state.length}\n场景：${state.scenes.join("、") || look.scene}\n补充：${(state.schemeOrigin === "create" ? state.createDraft : state.photoDraft) || "请结合实际甲面和美甲师建议调整。"}\nAI 演示参考，非真实制作效果。`;
      try { await navigator.clipboard.writeText(text); toast("方案文字已复制。"); burst(button, "medium"); }
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
  if (input.id === "other-person") {
    state.otherPerson = input.checked;
    clearTimeout(jobTimers.photo);
    state.generationByMode.photo = "idle";
    // 局部更新而非整页重渲染：保留 DOM 使滑块回弹动画与说明淡入过渡得以播放，且下方卡片零位移
    document.querySelector(".switch-block")?.classList.toggle("is-on", state.otherPerson);
    playSwitchElastic(input.closest(".switch-row"));
  }
  if (input.id === "selected-look") {
    /* 换款只复位结果面板与生成按钮，保持 select 焦点与页面其他区域不动 */
    state.selectedLook = byId(input.value).id;
    const wasGenerating = state.generationByMode.photo !== "idle";
    clearTimeout(jobTimers.photo);
    state.generationByMode.photo = "idle";
    if (wasGenerating) resetResultPanel("photo");
    else { const generate = $('[data-action="generate"][data-mode="photo"]'); generate?.removeAttribute("disabled"); generate?.removeAttribute("aria-busy"); }
  }
  if (input.id === "learn-toggle") { state.profileLearnDraft = input.checked; playSwitchElastic(input.closest(".switch-row")); }
  if (input.id === "onboarding-learn") { state.onboardingLearnDraft = input.checked; playSwitchElastic(input.closest(".switch-row")); }
  if (input.id === "publish-rights") { state.publishRights = input.checked; playSwitchElastic(input.closest(".switch-row")); }
  if (input.id === "publish-source") state.publishSource = input.value;
  if (["styles", "scenes"].includes(input.name)) state[input.name] = [...document.querySelectorAll(`input[name="${input.name}"]:checked`)].map((item) => item.value);
  if (input.name === "length") state.length = input.value;
  if (input.dataset.upload && input.files[0]) acceptFile(input.dataset.upload, input.files[0], input);
});
const hasFiles = (transfer) => transfer ? Array.from(transfer.types ?? []).includes("Files") || (transfer.files?.length ?? 0) > 0 : false;
const uploadBoxFrom = (element) => element?.closest?.(".upload-box") ?? null;
const visibleUploadBox = () => document.querySelector(".page-view .upload-box input[data-upload]")?.closest(".upload-box") ?? null;
document.addEventListener("dragover", (event) => {
  if (!hasFiles(event.dataTransfer)) return;
  event.preventDefault();
  uploadBoxFrom(event.target)?.classList.add("is-dragover");
});
document.addEventListener("dragleave", (event) => {
  const box = uploadBoxFrom(event.target);
  if (box && !box.contains(event.relatedTarget)) box.classList.remove("is-dragover");
});
document.addEventListener("drop", async (event) => {
  if (!hasFiles(event.dataTransfer)) return;
  event.preventDefault();
  const box = uploadBoxFrom(event.target);
  box?.classList.remove("is-dragover");
  const input = box?.querySelector("input[data-upload]");
  const file = event.dataTransfer?.files?.[0];
  if (input && file) await acceptFile(input.dataset.upload, file);
});
document.addEventListener("paste", (event) => {
  const file = event.clipboardData?.files?.[0];
  if (!file) return;
  const box = uploadBoxFrom(event.target) ?? visibleUploadBox();
  const input = box?.querySelector("input[data-upload]");
  if (!input) return;
  event.preventDefault();
  acceptFile(input.dataset.upload, file);
});
document.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  focusAfterRoute = false;
  if (form.id === "onboarding-form") {
    const step = Number(form.dataset.step);
    if (step < 4) { if (step === 3 && state.onboardingSummaryDraft === null && state.profile?.trim()) state.onboardingSummaryDraft = state.profile; navigate(`onboarding/${step + 1}`); }
    else {
      state.profile = $("#onboarding-summary").value.trim(); state.learned = $("#onboarding-learn").checked; state.profileDraft = state.profile; state.profileLearnDraft = state.learned; state.onboarded = true; persist();
      burst(form.querySelector('button[type=submit]'), "medium"); /* 按钮即将随导航移除，burst 先取坐标 */
      navigate("home"); toast("偏好已保存到本地预览，未调用语言模型。");
    }
  }
  if (form.id === "profile-form") { state.profile = $("#profile-text").value.trim(); state.learned = $("#learn-toggle").checked; state.profileDraft = state.profile; persist(); burst(form.querySelector('button[type=submit]'), "medium"); toast("偏好已更新到本地预览。"); }
  if (form.id === "publish-form") {
    if (!state.loggedIn) { showLogin(); return; }
    const title = $("#publish-title").value.trim();
    if (!title) { toast("请给作品起一个名字。"); return; }
    if (!state.uploads.publish) { toast("请先添加款式图片。"); return; }
    if (!$("#publish-rights").checked) { toast("请确认图片分享权利。"); return; }
    state.posts.push({ title, source: state.publishSource, description: $("#publish-text").value.trim(), url: state.uploads.publish.url });
    // 转移 URL 所有权，后续换图不会释放已发布的本地预览图片。
    state.uploads.publish = null; state.publishTitle = ""; state.publishDraft = ""; state.publishRights = false;
    burst(form.querySelector('button[type=submit]'), "heavy"); /* 重档：发布完成 */
    navigate("creator/me"); toast("本地发布布局已生成，照片没有上传或公开。");
  }
});
function releaseUploads() {
  for (const upload of Object.values(state.uploads)) if (upload) URL.revokeObjectURL(upload.url);
  for (const post of state.posts) URL.revokeObjectURL(post.url);
}
window.addEventListener("hashchange", () => {
  if (!pendingNavigation) { scrollPositions.set(renderedHash, window.scrollY); pendingNavigation = { restore: true }; }
  closeModal(); focusAfterRoute = true; render();
});
$("#sheet").addEventListener("cancel", (event) => { event.preventDefault(); closeModal(); });
$("#sheet").addEventListener("close", () => {
  if ($("#sheet").open) return;
  document.body.classList.remove("sheet-open");
  const trigger = modalTrigger;
  modalTrigger = null;
  if (trigger?.selector && trigger.hash === renderedHash) $(trigger.selector)?.focus({ preventScroll: true });
  updateViewport();
});
$("#sheet").addEventListener("click", (event) => {
  if (event.target !== event.currentTarget) return;
  const box = event.currentTarget.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeModal();
});
function toggleDetails(details) {
  const summary = details.querySelector("summary");
  if (!summary) return;
  if (reducedMotion.matches || !details.animate) { details.open = !details.open; return; }
  details.__detailsAnimation?.cancel();
  const collapsed = summary.getBoundingClientRect().height;
  details.style.height = ""; details.style.overflow = "";
  if (!details.open) {
    details.open = true;
    const expanded = details.getBoundingClientRect().height;
    details.style.overflow = "hidden";
    const animation = details.animate([{ height: `${collapsed}px` }, { height: `${expanded}px` }], { duration: 300, easing: "cubic-bezier(.22,.68,.2,1)" });
    details.__detailsAnimation = animation;
    animation.onfinish = () => { details.style.height = ""; details.style.overflow = ""; details.__detailsAnimation = null; };
  } else {
    const expanded = details.getBoundingClientRect().height;
    details.style.overflow = "hidden";
    const animation = details.animate([{ height: `${expanded}px` }, { height: `${collapsed}px` }], { duration: 260, easing: "cubic-bezier(.4,0,1,1)" });
    details.__detailsAnimation = animation;
    animation.onfinish = () => { details.open = false; details.style.height = ""; details.style.overflow = ""; details.__detailsAnimation = null; };
  }
}
document.addEventListener("click", (event) => {
  const summary = event.target.closest("details > summary");
  if (!summary || event.defaultPrevented) return;
  event.preventDefault();
  toggleDetails(summary.parentElement);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Tab" || event.key.startsWith("Arrow")) document.body.dataset.input = "keyboard";
  /* 按压回弹键盘路径（§2.1）：Enter/Space 与指针同参 */
  if (event.key !== "Enter" && event.key !== " ") return;
  pressControl(event.target.closest?.(pressTargets));
});
document.addEventListener("keyup", (event) => {
  if (event.key === "Enter" || event.key === " ") releaseAllPress();
});
document.addEventListener("focusout", releaseAllPress);
document.addEventListener("pointerdown", (event) => {
  document.body.dataset.input = ["touch", "pen"].includes(event.pointerType) ? "touch" : "mouse";
  /* 按压回弹＋水波（§2.1/§2.3）：按下即下沉，水波以落点为原点；反馈跟随指针而非控件中心 */
  const control = event.target.closest?.(pressTargets);
  if (!control || control.disabled || event.button !== 0) return;
  pressControl(control);
  spawnRipple(control, event.clientX, event.clientY);
}, { passive: true });
document.addEventListener("pointerup", (event) => { releasePress(event.target.closest?.(pressTargets)); });
document.addEventListener("pointercancel", (event) => { releasePress(event.target.closest?.(pressTargets)); });
document.addEventListener("pointerout", (event) => {
  const control = event.target.closest?.(pressTargets);
  if (control && !control.contains(event.relatedTarget)) releasePress(control);
});
/* 键盘激活的点击（detail===0）在控件中心补一次水波；capture 阶段执行，先于可能重渲染的动作处理器 */
document.addEventListener("click", (event) => {
  if (event.detail !== 0) return;
  const control = event.target.closest?.(rippleTargets);
  if (control && !control.disabled) spawnRipple(control);
}, true);
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
