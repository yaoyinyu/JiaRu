import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * 弹层与状态反馈共享组件合同（源码契约断言，frontend-interaction-redesign-plan §2.2/§10.2）：
 * 以源码文本锁定语义与交互实现，防止未来重构无声丢失：
 *  - AppDialog：role="dialog" + aria-modal + 标题/描述编程关联、Portal 到 document.body（SSR 安全）、
 *    Escape/遮罩关闭、Tab 焦点圈定（走 dialog-focus 纯函数）、初始焦点 data-autofocus 标记、
 *    关闭后焦点恢复、背景滚动锁定（多实例计数）、overscroll-behavior、reduced-motion 降级；
 *  - ConfirmDialog：默认焦点在取消钮（安全默认）、data-autofocus 标记、Escape/遮罩走 onCancel、
 *    破坏性确认使用珊瑚深色实底；
 *  - StatusRegion：role/aria-live 按 status 映射、idle 不渲染、loading 省略号、
 *    live region 内禁止计时器/秒数、severity 色系与全站一致。
 */

/** 按仓库根（process.cwd()）读取源文件为字符串 */
const readSource = (...segments: string[]): string =>
  readFileSync(join(process.cwd(), ...segments), "utf8");

const appDialogTsx = readSource("src", "components", "ui", "AppDialog.tsx");
const appDialogCss = readSource("src", "components", "ui", "AppDialog.module.css");
const confirmDialogTsx = readSource("src", "components", "ui", "ConfirmDialog.tsx");
const statusRegionTsx = readSource("src", "components", "ui", "StatusRegion.tsx");
const dialogFocusTs = readSource("src", "components", "ui", "dialog-focus.ts");

/** 截取 text 中自 startIdx 起第一个花括号配平的 {...} 块（含花括号本身） */
function cssBlock(text: string, startIdx: number): string {
  const open = text.indexOf("{", startIdx);
  assert.notEqual(open, -1, "CSS 规则缺少 {");
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(open, i + 1);
    }
  }
  return assert.fail("CSS 规则花括号未配平");
}

/** 命中行首选择器的第一个规则块（^\s* 锚定，避免误配复合选择器） */
function cssRule(text: string, selector: RegExp): string {
  const at = text.search(selector);
  assert.notEqual(at, -1, `缺少 CSS 规则：${String(selector)}`);
  return cssBlock(text, at);
}

test("AppDialog：client 组件 + dialog 语义属性（role/aria-modal/aria-labelledby/aria-describedby）", () => {
  assert.ok(appDialogTsx.startsWith('"use client"'), "AppDialog 必须是 client 组件");
  assert.match(appDialogTsx, /role="dialog"/, "必须声明 role=dialog");
  assert.match(appDialogTsx, /aria-modal="true"/, "必须声明 aria-modal");
  assert.match(appDialogTsx, /aria-labelledby=\{titleId\}/, "必须以 aria-labelledby 关联标题");
  assert.match(
    appDialogTsx,
    /aria-describedby=\{description \? descriptionId : undefined\}/,
    "描述文本必须以 aria-describedby 编程关联（仅在有描述时）"
  );
  assert.match(appDialogTsx, /<h2 id=\{titleId\} className=\{styles\.title\}>/, "标题必须是 h2 且绑定 id");
});

test("AppDialog：createPortal 渲染到 document.body 且 SSR 安全", () => {
  assert.match(appDialogTsx, /import \{ createPortal \} from "react-dom"/, "必须使用 react-dom Portal");
  assert.match(appDialogTsx, /createPortal\(/, "必须经 createPortal 挂载");
  assert.match(appDialogTsx, /,\s*document\.body\s*\)/, "Portal 容器必须是 document.body");
  assert.match(appDialogTsx, /if \(!open\) return null;/, "关闭态不得渲染任何内容");
  assert.match(
    appDialogTsx,
    /typeof document === "undefined"/,
    "必须守卫服务端环境（SSR 安全）"
  );
});

test("AppDialog：Escape 与背景遮罩关闭，弹层内容点击不冒泡关闭", () => {
  assert.match(
    appDialogTsx,
    /event\.key === "Escape" && closeOnEsc/,
    "Escape 必须受 closeOnEsc 开关控制"
  );
  assert.match(
    appDialogTsx,
    /event\.target === event\.currentTarget/,
    "遮罩点击必须做命中判断（只认遮罩自身）"
  );
  assert.match(appDialogTsx, /if \(!closeOnOutside\) return;/, "遮罩关闭必须受 closeOnOutside 开关控制");
  const panelClickStart = appDialogTsx.indexOf("const handlePanelClick");
  assert.notEqual(panelClickStart, -1, "缺少弹层内容点击处理器");
  const panelClickEnd = appDialogTsx.indexOf("if (!open)", panelClickStart);
  const panelClick = appDialogTsx.slice(panelClickStart, panelClickEnd);
  assert.match(panelClick, /event\.stopPropagation\(\)/, "弹层内容点击必须阻止冒泡到遮罩");
});

test("AppDialog：Tab/Shift+Tab 焦点圈定走 dialog-focus 纯函数", () => {
  const importMatch = appDialogTsx.match(/import\s*\{([^}]*)\}\s*from\s*"\.\/dialog-focus"/);
  assert.ok(importMatch, "必须从 ./dialog-focus 导入焦点纯逻辑");
  const names = importMatch![1].split(",").map((item) => item.trim());
  for (const name of [
    "describeFocusCandidate",
    "isFocusableCandidate",
    "nextCyclicIndex",
    "selectInitialFocusIndex",
  ]) {
    assert.ok(names.includes(name), `导入清单缺少 ${name}`);
  }
  assert.match(appDialogTsx, /if \(event\.key !== "Tab"\) return;/, "Tab 之外的按键不得拦截");
  assert.match(
    appDialogTsx,
    /nextCyclicIndex\(targets\.length, activeIndex, event\.shiftKey \? -1 : 1\)/,
    "焦点循环必须由 nextCyclicIndex 纯函数决策"
  );
  const trapStart = appDialogTsx.indexOf("const handleKeyDown");
  assert.notEqual(trapStart, -1, "缺少 keydown 焦点圈定处理器");
  const trapEnd = appDialogTsx.indexOf("const handleOverlayClick", trapStart);
  const trap = appDialogTsx.slice(trapStart, trapEnd);
  assert.match(trap, /targets\.length === 0/, "空焦点圈分支必须显式处理");
  assert.match(trap, /event\.preventDefault\(\)/, "圈定内移动焦点必须 preventDefault");
  assert.match(trap, /panel\.focus\(\)/, "无可聚焦元素时焦点必须按在面板容器上");
});

test("AppDialog：初始焦点按 initialFocus 落到 data-autofocus 标记或第一个候选", () => {
  assert.match(appDialogTsx, /initialFocus = "first"/, "initialFocus 默认必须是 first");
  assert.match(appDialogTsx, /selectInitialFocusIndex\(/, "初始焦点必须走选择纯函数");
  assert.match(appDialogTsx, /targets\.map\(describeFocusCandidate\)/, "候选必须先过最小结构描述");
  assert.match(
    dialogFocusTs,
    /getAttribute\("data-autofocus"\)/,
    "标记必须读取 data-autofocus 属性"
  );
  assert.match(
    dialogFocusTs,
    /autoFocusMark === initialFocus/,
    "confirm/cancel 必须按 data-autofocus 标记命中"
  );
  assert.match(appDialogTsx, /targets\[targetIndex\]\.focus\(\)/, "命中标记时聚焦该元素");
  assert.match(appDialogTsx, /panel\.focus\(\)/, "无候选时回退聚焦面板容器");
});

test("AppDialog：关闭后焦点恢复与背景滚动锁定（多实例安全计数）", () => {
  assert.match(
    appDialogTsx,
    /document\.activeElement instanceof HTMLElement/,
    "打开时必须记录此前活动元素"
  );
  assert.match(
    appDialogTsx,
    /restoreTarget && restoreTarget\.isConnected/,
    "恢复目标必须仍连接在文档中才聚焦"
  );
  assert.match(appDialogTsx, /restoreTarget\.focus\(\)/, "关闭后必须恢复焦点");
  assert.match(appDialogTsx, /scrollLockCount \+= 1/, "滚动锁必须计数递增");
  assert.match(appDialogTsx, /scrollLockCount -= 1/, "滚动锁必须计数递减");
  assert.match(
    appDialogTsx,
    /scrollLockCount === 1[\s\S]*?document\.body\.style\.overflow = "hidden"/,
    "首个实例才加锁（多实例安全）"
  );
  assert.match(
    appDialogTsx,
    /scrollLockCount === 0[\s\S]*?document\.body\.style\.overflow = ""/,
    "最后一个实例解锁时清除锁定"
  );
});

test("AppDialog 样式：新拟态视觉与 overscroll-behavior: contain", () => {
  const overlay = cssRule(appDialogCss, /^\s*\.overlay\s*\{/m);
  assert.match(overlay, /position: fixed/, "遮罩必须全屏固定");
  assert.match(overlay, /z-index:\s*\d+/, "遮罩必须有明确层级");
  assert.match(overlay, /rgba\(41,\s*42,\s*39/, "遮罩必须用墨色半透明（--ink 的 rgb）");
  assert.match(overlay, /overscroll-behavior:\s*contain/, "遮罩必须约束滚动链");
  const panel = cssRule(appDialogCss, /^\s*\.panel\s*\{/m);
  assert.match(panel, /background: var\(--paper\)/, "面板必须用纸底");
  assert.match(panel, /box-shadow: var\(--neu-out-lg\)/, "面板必须用大号新拟态外阴影");
  assert.match(panel, /border-radius:\s*\d+px/, "面板必须大圆角");
  const title = cssRule(appDialogCss, /^\s*\.title\s*\{/m);
  assert.match(title, /font-family: var\(--serif\)/, "标题必须衬线字体");
  const body = cssRule(appDialogCss, /^\s*\.body\s*\{/m);
  assert.match(body, /overflow-y: auto/, "内容区必须可滚动");
  assert.match(body, /overscroll-behavior:\s*contain/, "内容区必须约束滚动链");
  assert.ok(
    (appDialogCss.match(/overscroll-behavior:\s*contain/g) ?? []).length >= 2,
    "遮罩与内容至少两处约束 overscroll"
  );
});

test("AppDialog 样式：动效只用 transform/opacity，无 transition: all，reduced-motion 降级", () => {
  // 匹配前剥离注释：断言只针对真实声明，头部注释中的「禁用 transition: all」字样不算违规
  const appDialogCssCode = appDialogCss.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(appDialogCssCode, /transition:\s*all/, "禁止 transition: all");
  const keyframeBlocks: string[] = [];
  let searchFrom = 0;
  for (;;) {
    const at = appDialogCss.indexOf("@keyframes", searchFrom);
    if (at === -1) break;
    keyframeBlocks.push(cssBlock(appDialogCss, at));
    searchFrom = at + 1;
  }
  assert.ok(keyframeBlocks.length >= 2, "遮罩与面板应各有一个入场动画");
  for (const block of keyframeBlocks) {
    const properties = Array.from(block.matchAll(/([a-zA-Z-]+)\s*:/g), (match) => match[1]);
    for (const property of properties) {
      assert.ok(
        property === "opacity" || property === "transform",
        `动画属性只允许 opacity/transform，发现：${property}`
      );
    }
  }
  const reduceAt = appDialogCss.indexOf("@media (prefers-reduced-motion: reduce)");
  assert.notEqual(reduceAt, -1, "缺少 prefers-reduced-motion 降级块");
  const reduceBlock = cssBlock(appDialogCss, reduceAt);
  assert.match(reduceBlock, /\.overlay/, "reduced-motion 须覆盖遮罩");
  assert.match(reduceBlock, /\.panel/, "reduced-motion 须覆盖面板");
  assert.match(reduceBlock, /animation:\s*none/, "reduced-motion 下必须 animation: none");
});

test("ConfirmDialog：基于 AppDialog，默认焦点在取消钮（安全默认）", () => {
  assert.ok(confirmDialogTsx.startsWith('"use client"'), "ConfirmDialog 必须是 client 组件");
  assert.match(confirmDialogTsx, /from "\.\/AppDialog"/, "必须复用 AppDialog 基座");
  assert.match(confirmDialogTsx, /initialFocus="cancel"/, "初始焦点必须默认落在取消钮");
  assert.match(confirmDialogTsx, /data-autofocus="cancel"/, "取消钮必须带 cancel 标记");
  assert.match(confirmDialogTsx, /data-autofocus="confirm"/, "确认钮必须带 confirm 标记");
});

test("ConfirmDialog：确认/取消分流与破坏性配色、默认文案", () => {
  assert.match(confirmDialogTsx, /onClose=\{onCancel\}/, "Escape/遮罩关闭必须走 onCancel");
  assert.match(confirmDialogTsx, /onClick=\{onCancel\}/, "取消钮必须走 onCancel");
  assert.match(confirmDialogTsx, /onClick=\{onConfirm\}/, "确认钮必须走 onConfirm");
  assert.equal(
    (confirmDialogTsx.match(/type="button"/g) ?? []).length,
    2,
    "两个动作按钮都必须是 type=button"
  );
  assert.match(confirmDialogTsx, /confirmLabel = "确认"/, "确认钮默认文案必须是「确认」");
  assert.match(confirmDialogTsx, /cancelLabel = "取消"/, "取消钮默认文案必须是「取消」");
  assert.match(confirmDialogTsx, /destructive = false/, "destructive 默认关闭");
  assert.match(
    confirmDialogTsx,
    /var\(--coral-deep\)/,
    "破坏性确认钮必须用珊瑚深色实底"
  );
});

test("StatusRegion：role/aria-live 按 status 映射，idle 不渲染", () => {
  assert.ok(statusRegionTsx.startsWith('"use client"'), "StatusRegion 必须是 client 组件");
  assert.match(
    statusRegionTsx,
    /interface StatusRegionProps\s*\{[^}]*status: StatusRegionStatus[^}]*message\?: string[^}]*severity\?: StatusRegionSeverity[^}]*className\?: string/,
    "props 必须包含 status/message/severity/className"
  );
  assert.match(statusRegionTsx, /status === "idle"/, "必须显式处理 idle");
  assert.match(
    statusRegionTsx,
    /if \(status === "idle"\) return null;/,
    "idle 必须不渲染任何内容"
  );
  assert.match(
    statusRegionTsx,
    /role=\{isError \? "alert" : "status"\}/,
    "error 用 role=alert，loading/success 用 role=status"
  );
  assert.match(
    statusRegionTsx,
    /aria-live=\{isError \? undefined : "polite"\}/,
    "loading/success 必须 aria-live=polite（error 由 role=alert 隐含 assertive）"
  );
});

test("StatusRegion：loading 省略号与 live region 无计时器约束", () => {
  assert.match(
    statusRegionTsx,
    /status === "loading" \? withLoadingEllipsis\(message\)/,
    "loading 文案必须经省略号归一"
  );
  assert.match(statusRegionTsx, /endsWith\("…"\)/, "已有省略号不得重复追加");
  assert.match(statusRegionTsx, /\$\{base\}…/, "缺失省略号时以 … 结尾");
  assert.doesNotMatch(
    statusRegionTsx,
    /setTimeout|setInterval|Date\.now/,
    "live region 内禁止计时器/秒数（读屏会反复播报）"
  );
  assert.ok(
    statusRegionTsx.includes("live region 约束"),
    "必须以注释登记 live region 内禁止计时器的约束"
  );
});

test("StatusRegion：severity 色系与全站一致", () => {
  // success 沿用现有页面 emerald-50/700（ar-tryon 同色阶）
  assert.match(statusRegionTsx, /border-emerald-200 bg-emerald-50 text-emerald-700/);
  // warning 沿用现有页面 amber-50/800（editor 同色阶）
  assert.match(statusRegionTsx, /border-amber-200 bg-amber-50 text-amber-800/);
  // error 沿用现有页面 red-50/600（login 同色阶）
  assert.match(statusRegionTsx, /border-red-100 bg-red-50 text-red-600/);
  // info 用墨/muted 与全站 surface 底
  assert.match(statusRegionTsx, /border-\[var\(--line\)\] bg-\[var\(--surface\)\] text-\[var\(--muted\)\]/);
  assert.match(statusRegionTsx, /rounded-2xl border px-4 py-3 text-sm leading-5/, "视觉与全站圆角/边框/字号一致");
});
