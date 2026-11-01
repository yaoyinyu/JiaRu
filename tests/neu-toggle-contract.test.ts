import assert from "node:assert/strict";
import test from "node:test";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * 新拟态拨动开关交互合同（源码契约断言）：
 * 以源码文本断言锁定动效与可达性关键实现，防止未来重构无声丢失：
 *  - 弹簧缓动：--knob-x 过渡 340ms + var(--ease-spring)；
 *  - 磁吸：.rowDragging 保留 --knob-pull 短过渡，globals.css @property 注册为 <length>；
 *  - 挤压回弹：rowStretching→rowSettling 两阶段 120ms/80ms setTimeout 链；
 *  - 可达性：真实 <input type="checkbox">、.row:focus-within .track focus 环、
 *    prefers-reduced-motion 降级（.track/.knob transition: none）；
 *  - 拖拽决策走纯函数 @/lib/ui/toggle-drag（resolveDragFrame + NEU_TOGGLE_TRAVEL）；
 *  - 使用方 NailAnalysisForm 已迁移且提示条 grid-rows 平滑展开；
 *  - src 全站原生 checkbox 仅允许存在于 NeuToggle 组件内（tests 目录除外）。
 */

/** 按仓库根（process.cwd()）读取源文件为字符串 */
const readSource = (...segments: string[]): string =>
  readFileSync(join(process.cwd(), ...segments), "utf8");

const toggleTsx = readSource("src", "components", "NeuToggle.tsx");
const toggleCss = readSource("src", "components", "NeuToggle.module.css");
const dragLib = readSource("src", "lib", "ui", "toggle-drag.ts");
const globalsCss = readSource("src", "app", "globals.css");
const formTsx = readSource("src", "components", "NailAnalysisForm.tsx");

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

/** 命中行首选择器的规则块（^\s* 锚定，避免 .knob 误配 .rowOn .knob 等复合选择器） */
function cssRule(text: string, selector: RegExp): string {
  const at = text.search(selector);
  assert.notEqual(at, -1, `缺少 CSS 规则：${String(selector)}`);
  return cssBlock(text, at);
}

/** 递归收集 dir 下 .tsx 文件的相对 POSIX 路径，跳过 node_modules/.next/tests 目录 */
function collectTsxFiles(dir: string, base: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next" || entry.name === "tests") {
        continue;
      }
      collectTsxFiles(join(dir, entry.name), base, out);
    } else if (entry.isFile() && entry.name.endsWith(".tsx")) {
      out.push(join(dir, entry.name).slice(base.length + 1).replaceAll("\\", "/"));
    }
  }
  return out;
}

test("弹簧缓动：滑块位移 --knob-x 过渡为 340ms 弹簧曲线", () => {
  const knob = cssRule(toggleCss, /^\s*\.knob\s*\{/m);
  assert.match(
    knob,
    /--knob-x\s+340ms\s+var\(--ease-spring\)/,
    "松手吸附/回弹必须走 340ms 弹簧过渡（过冲动效合同）"
  );
});

test("磁吸：拖拽态保留 --knob-pull 短过渡，@property 注册为 <length>", () => {
  // 拖拽中：位置跟手（--knob-x 无过渡），磁吸偏置保留短过渡产生「吸引倾斜」
  const dragging = cssRule(toggleCss, /^\s*\.rowDragging\s[^{]*\{/m);
  assert.match(
    dragging,
    /--knob-pull\s+\d+ms\s+var\(--ease-press\)/,
    "拖拽中必须保留 --knob-pull 短过渡以产生吸引倾斜"
  );
  assert.doesNotMatch(
    dragging,
    /--knob-x/,
    "拖拽中 --knob-x 必须无过渡（跟手），位移过渡只留给松手后的弹簧吸附"
  );
  const propertyPattern = (name: string): RegExp =>
    new RegExp(`@property\\s+${name}\\s*\\{[^}]*syntax:\\s*"<length>"`);
  for (const name of ["--knob-x", "--knob-pull"]) {
    assert.match(
      globalsCss,
      propertyPattern(name),
      `globals.css 必须注册 ${name} 为 <length>（自定义属性可参与 transition 的前提）`
    );
  }
});

test("挤压回弹：rowStretching→rowSettling 两阶段 120ms/80ms 编排", () => {
  const start = toggleTsx.indexOf("const playElastic");
  assert.notEqual(start, -1, "缺少 playElastic 弹性编排函数");
  const end = toggleTsx.indexOf("const handleCheckedChange", start);
  assert.notEqual(end, -1, "playElastic 函数边界定位失败");
  const elastic = toggleTsx.slice(start, end);
  assert.ok(elastic.includes("styles.rowStretching"), "缺少起步拉伸阶段 rowStretching");
  assert.ok(elastic.includes("styles.rowSettling"), "缺少落位微压阶段 rowSettling");
  assert.equal((elastic.match(/setTimeout/g) ?? []).length, 2, "必须由两级 setTimeout 链编排");
  assert.match(elastic, /\},\s*120\)/, "起步拉伸须为 120ms 外层定时");
  assert.match(elastic, /,\s*80\)\)/, "落位微压须为 80ms 内层定时");
  assert.ok(
    elastic.includes("(prefers-reduced-motion: reduce)"),
    "reduced-motion 用户必须跳过挤压回弹编排"
  );
  // 两个阶段的形变目标类必须真实存在于样式表
  // 两阶段形变规则为复合选择器（.rowStretching .knob），与 .rowDragging 同构
  const stretching = cssRule(toggleCss, /^\s*\.rowStretching\s[^{]*\{/m);
  const settling = cssRule(toggleCss, /^\s*\.rowSettling\s[^{]*\{/m);
  assert.match(stretching, /--knob-sx/, "rowStretching 须改写 --knob-sx 产生横向拉伸");
  assert.match(settling, /--knob-sy/, "rowSettling 须改写 --knob-sy 产生纵向微压");
});

test("可达性：真实 checkbox、轨道 focus 环与 reduced-motion 降级", () => {
  assert.match(
    toggleTsx,
    /<input\s+type="checkbox"/,
    "必须渲染真实 <input type=checkbox>（label 原生切换 + 键盘空格可达）"
  );
  assert.ok(toggleTsx.includes("className={styles.input}"), "checkbox 须绑定视觉隐藏的 .input 样式");
  const inputRule = cssRule(toggleCss, /^\s*\.input\s*\{/m);
  assert.doesNotMatch(inputRule, /display:\s*none/, "隐藏 input 不得 display:none（须保持可聚焦）");
  const focusRing = cssRule(toggleCss, /^\s*\.row:focus-within \.track\s*\{/m);
  assert.match(focusRing, /outline/, "focus 环必须落在轨道上（.row:focus-within .track outline）");
  const reduceAt = toggleCss.indexOf("@media (prefers-reduced-motion: reduce)");
  assert.notEqual(reduceAt, -1, "缺少 prefers-reduced-motion 降级块");
  const reduceBlock = cssBlock(toggleCss, reduceAt);
  assert.match(
    reduceBlock,
    /\.track[\s\S]*\.knob\s*\{[\s\S]*transition:\s*none/,
    "reduced-motion 下 .track/.knob 必须 transition: none"
  );
});

test("拖拽决策走纯函数：NeuToggle 只依赖 @/lib/ui/toggle-drag", () => {
  const importMatch = toggleTsx.match(/import\s*\{([^}]*)\}\s*from\s*"@\/lib\/ui\/toggle-drag"/);
  assert.ok(importMatch, "必须从 @/lib/ui/toggle-drag 导入拖拽决策");
  const names = importMatch![1].split(",").map((item) => item.trim());
  for (const name of ["NEU_TOGGLE_TRAVEL", "resolveDragFrame"]) {
    assert.ok(names.includes(name), `导入清单缺少 ${name}`);
  }
  assert.match(dragLib, /export\s+function\s+resolveDragFrame/, "toggle-drag 须导出纯函数 resolveDragFrame");
  assert.match(dragLib, /export\s+const\s+NEU_TOGGLE_TRAVEL/, "toggle-drag 须导出行程常量 NEU_TOGGLE_TRAVEL");
});

test("使用方迁移：NailAnalysisForm 无原生 checkbox 且提示条平滑展开", () => {
  assert.ok(!formTsx.includes('type="checkbox"'), "使用方不得再直接渲染原生 checkbox");
  assert.ok(formTsx.includes("<NeuToggle"), "使用方须改用 <NeuToggle> 组件");
  assert.ok(formTsx.includes("grid-rows-[0fr]"), "提示条收起态缺少 grid-rows-[0fr]");
  assert.ok(formTsx.includes("grid-rows-[1fr]"), "提示条展开态缺少 grid-rows-[1fr]");
  assert.ok(formTsx.includes("aria-hidden"), "提示条收起时须对辅助技术隐藏");
});

test("全站无残留：src 下原生 checkbox 仅允许存在于 NeuToggle 组件", () => {
  const srcDir = join(process.cwd(), "src");
  const holders = collectTsxFiles(srcDir, srcDir).filter((file) =>
    readFileSync(join(srcDir, file), "utf8").includes('type="checkbox"')
  );
  // 语义 checkbox 的唯一合法宿主是 NeuToggle 自身（见可达性合同）；
  // 其余任何 .tsx 出现 type="checkbox" 即视为迁移残留。
  assert.deepEqual(
    holders,
    ["components/NeuToggle.tsx"],
    "原生 checkbox 只能出现在 NeuToggle 组件内，tests 目录除外"
  );
});
