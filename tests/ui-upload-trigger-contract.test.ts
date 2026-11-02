import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * UploadTrigger 组件源码合同（frontend-interaction-redesign-plan §2.2 / §10.2）：
 * 以源码文本断言锁定交互与可达性关键实现，防止未来重构无声丢失：
 *  - 真实 <button type="button"> 承载交互语义（可聚焦、Enter/Space 原生激活）；
 *  - <input type="file" class sr-only> 为 button 的兄弟节点，不在 button 内部；
 *  - input onChange 无论成功失败都重置 value（同一文件可重复选择）；
 *  - .root:focus-within 显示全站珊瑚 outline 焦点环；
 *  - disabled/loading 同时禁用按钮与文件输入，loading 有 spinner + loadingLabel；
 *  - 动效合同：无 transition: all、过渡只走 transform/opacity、keyframes 只动 transform；
 *  - prefers-reduced-motion 降级（transition: none、spinner animation: none）；
 *  - 键盘可达依赖 button 原生语义，不得出现自造 onKeyDown 键盘分支。
 */

/** 按仓库根（process.cwd()）读取源文件为字符串 */
const readSource = (...segments: string[]): string =>
  readFileSync(join(process.cwd(), ...segments), "utf8");

const triggerTsx = readSource("src", "components", "ui", "UploadTrigger.tsx");
const triggerCss = readSource("src", "components", "ui", "UploadTrigger.module.css");

/** 剥离块注释后的 CSS 代码：断言只看代码本身，不受注释措辞干扰 */
const cssCode = triggerCss.replace(/\/\*[\s\S]*?\*\//g, "");

/** 组件 JSX 片段（自 return ( 起）：结构断言排除文件头注释里的接口描述文字 */
const markupStart = triggerTsx.indexOf("return (");
assert.notEqual(markupStart, -1, "UploadTrigger 缺少 return ( 渲染段");
const markup = triggerTsx.slice(markupStart);

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

/** 命中行首选择器的规则块 */
function cssRule(text: string, selector: RegExp): string {
  const at = text.search(selector);
  assert.notEqual(at, -1, `缺少 CSS 规则：${String(selector)}`);
  return cssBlock(text, at);
}

test("客户端组件指令与真实 button：type=button 原生承载键盘与读屏语义", () => {
  assert.match(triggerTsx, /^"use client";/, "组件必须声明 \"use client\"");
  assert.match(markup, /<button\s+type="button"/, "交互宿主必须是真实 <button type=button>");
  assert.equal((markup.match(/<button/g) ?? []).length, 1, "渲染段必须只有这一个 button");
  assert.doesNotMatch(markup, /<label/, "不得再用 label 包裹方案");
  assert.doesNotMatch(triggerTsx, /onKeyDown/, "button 原生 Enter/Space 已可达，禁止自造键盘分支");
  assert.match(markup, /aria-label=\{ariaLabel\}/, "aria-label prop 必须透传到按钮");
});

test("兄弟结构：<input type=file class sr-only> 存在于 button 之后，不在 button 内部", () => {
  const buttonOpen = markup.indexOf("<button");
  const buttonClose = markup.indexOf("</button>");
  const inputOpen = markup.indexOf("<input");
  assert.notEqual(buttonClose, -1, "缺少 button 闭合标签");
  assert.notEqual(inputOpen, -1, "缺少 file input 元素");
  const buttonBody = markup.slice(buttonOpen, buttonClose);
  assert.doesNotMatch(buttonBody, /<input/, "button 内部不得嵌套 file input（兄弟结构合同）");
  assert.ok(
    inputOpen > buttonClose,
    "file input 必须出现在 button 闭合之后（兄弟节点）"
  );
  assert.match(markup, /<input\s*\n\s*ref=\{inputRef\}/, "input 必须绑定 inputRef");
  assert.match(markup, /type="file"/, "input type 必须是 file");
  assert.match(markup, /className="sr-only"/, "file input 必须使用 sr-only 视觉隐藏");
  assert.match(markup, /tabIndex=\{-1\}/, "file input 不得进入 Tab 序（焦点由 button 承担）");
  assert.match(markup, /accept=\{accept\}/, "accept prop 必须透传");
  assert.match(markup, /multiple=\{multiple\}/, "multiple prop 必须透传");
});

test("onChange 后重置 value：同一文件可重复选择，且重置先于 onFiles 回调", () => {
  const onChangeStart = triggerTsx.indexOf("handleInputChange");
  assert.notEqual(onChangeStart, -1, "缺少 handleInputChange 处理器");
  const resetAt = triggerTsx.indexOf('input.value = "";', onChangeStart);
  assert.notEqual(resetAt, -1, "onChange 内必须重置 input.value 为空");
  const onFilesCall = triggerTsx.indexOf("onFiles(", onChangeStart);
  assert.notEqual(onFilesCall, -1, "onChange 内必须调用 onFiles");
  assert.ok(
    resetAt < onFilesCall,
    "value 重置必须发生在 onFiles 回调之前（回调抛错也不影响重复选择）"
  );
  assert.match(
    triggerTsx,
    /multiple \? files : files\.slice\(0, 1\)/,
    "multiple 时传全部文件，否则只取第一个"
  );
});

test("focus-within 焦点环：容器内获得焦点时按钮显示全站珊瑚 outline", () => {
  const focusRing = cssRule(cssCode, /^\s*\.root:focus-within \.button\s*\{/m);
  assert.match(focusRing, /outline:\s*2px solid var\(--coral\)/, "焦点环必须复用全站珊瑚 outline");
  assert.match(focusRing, /outline-offset/, "焦点环必须有 outline-offset");
});

test("disabled/loading 行为：按钮与文件输入同时禁用，loading 展示 spinner 与文案", () => {
  assert.match(triggerTsx, /const inactive = disabled \|\| loading;/, "必须由 disabled/loading 推导统一禁用态");
  const disabledCount = (markup.match(/disabled=\{inactive\}/g) ?? []).length;
  assert.ok(disabledCount >= 2, "button 与 file input 都必须绑定 disabled={inactive}");
  assert.match(markup, /disabled=\{inactive\}\s*\n\s*aria-busy/, "button 的 disabled 后必须紧跟 aria-busy");
  assert.match(markup, /aria-busy=\{loading \|\| undefined\}/, "loading 时必须输出 aria-busy");
  assert.match(triggerTsx, /loadingLabel = "处理中…"/, "loadingLabel 默认值必须是「处理中…」");
  assert.match(markup, /className=\{styles\.spinner\}\s+aria-hidden="true"/, "spinner 必须对辅助技术隐藏");
  assert.match(markup, /<span>\{loadingLabel\}<\/span>/, "loading 文案必须是真实文本节点");
});

test("动效合同：无 transition: all，过渡只走 transform/opacity，keyframes 只动 transform", () => {
  assert.doesNotMatch(cssCode, /transition:\s*all/, "禁止 transition: all");

  const transitions = [...cssCode.matchAll(/transition:\s*([^;]+);/g)].map((m) => m[1]);
  assert.ok(transitions.length >= 1, "缺少 transition 声明（按压反馈合同）");
  for (const value of transitions) {
    const properties = value.split(",").map((part) => part.trim());
    for (const prop of properties) {
      if (prop === "none") continue; // reduced-motion 的关闭过渡声明，不是动画属性
      assert.match(
        prop,
        /^(transform|opacity)\b/,
        `transition 属性只允许 transform/opacity，发现：${prop}`
      );
    }
  }

  const keyframeAt = cssCode.indexOf("@keyframes");
  assert.notEqual(keyframeAt, -1, "缺少 spinner @keyframes");
  const keyframes = cssBlock(cssCode, keyframeAt);
  const animatedProps = [...keyframes.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
  assert.ok(animatedProps.includes("transform"), "spinner 动画必须使用 transform");
  for (const prop of animatedProps) {
    assert.equal(prop, "transform", `keyframes 内只允许动画 transform，发现：${prop}`);
  }
});

test("prefers-reduced-motion 降级：关闭过渡与 spinner 旋转动画", () => {
  const reduceAt = cssCode.indexOf("@media (prefers-reduced-motion: reduce)");
  assert.notEqual(reduceAt, -1, "缺少 prefers-reduced-motion 降级块");
  const reduceBlock = cssBlock(cssCode, reduceAt);
  assert.match(reduceBlock, /\.button\s*\{[\s\S]*?transition:\s*none/, "reduced-motion 下 .button 必须 transition: none");
  assert.match(reduceBlock, /\.spinner\s*\{[\s\S]*?animation:\s*none/, "reduced-motion 下 .spinner 必须 animation: none");
});

test("新拟态视觉：凸起默认、按压转凹陷、hover 增强，尺寸令牌来自全局变量", () => {
  const button = cssRule(cssCode, /^\s*\.button\s*\{/m);
  assert.match(button, /box-shadow:\s*var\(--neu-out-md\)/, "默认态必须是 --neu-out-* 凸起");
  assert.match(button, /border-radius:\s*18px/, "必须有圆角");
  assert.match(button, /min-height:\s*44px/, "触控目标不得低于 44px");
  assert.match(button, /font-size:\s*14px/, "主操作字号不得低于 14px");
  const active = cssRule(cssCode, /^\s*\.button:active:not\(:disabled\)\s*\{/m);
  assert.match(active, /var\(--neu-in-sm\)/, "按压必须转为 --neu-in-* 凹陷");
  assert.match(active, /transform/, "按压反馈必须走 transform，不得产生布局位移");
  const hover = cssRule(cssCode, /^\s*\.button:hover:not\(:disabled\)\s*\{/m);
  assert.match(hover, /var\(--neu-out-hover\)/, "hover 必须使用 --neu-out-hover 增强阴影");
});
