import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  pushEditorSnapshot,
  shouldCoalesceHistory,
  undoEditorSnapshot,
  HISTORY_COALESCE_WINDOW_MS,
  type EditorSnapshot,
} from "../src/lib/editor-texture-state.ts";
import {
  clampToImageBounds,
  NUDGE_STEP_LARGE_PX,
  NUDGE_STEP_PX,
  partitionExportTextures,
  type NailPlacement,
} from "../src/lib/canvas/placements.ts";

// ── 快照撤销栈（§5.6）：frames + placements 一起 push / undo ──

interface FakeFrame {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
}

function fakeFrame(id: string, assignedFinger: number | null): FakeFrame {
  return { id, cx: 10, cy: 20, angle: 0, nl: 60, nw: 30, assignedFinger };
}

function fakePlacement(id: string, frameId: string): NailPlacement {
  return {
    id,
    frameId,
    textureKey: "set-a/0",
    textureSrc: "/nail-textures/set-a/finger-1.png",
    aspect: 1.2,
    angle: 0,
    baseCx: 10,
    baseCy: 20,
    baseLength: 60,
    baseWidth: 30,
    cx: 10,
    cy: 20,
    length: 72,
    width: 30,
    adjust: { lengthScale: 1, widthScale: 1, rootOffset: 0 },
  };
}

test("pushEditorSnapshot records frames and placements together; undo restores both", () => {
  const initial: EditorSnapshot = {
    frames: [fakeFrame("f1", 0)],
    placements: [],
  };
  let history = pushEditorSnapshot([], initial);
  assert.equal(history.length, 1);

  const afterPlace: EditorSnapshot = {
    frames: [fakeFrame("f1", 0), fakeFrame("f2", 1)],
    placements: [fakePlacement("placement-f1", "f1")],
  };
  history = pushEditorSnapshot(history, afterPlace);
  assert.equal(history.length, 2);

  const firstUndo = undoEditorSnapshot(history);
  assert.ok(firstUndo);
  // 撤销后恢复到「贴合后」的完整状态（快照在变更前压入，栈顶是最近一次变更前）。
  assert.equal(firstUndo.snapshot.frames.length, 2);
  assert.equal(firstUndo.snapshot.placements.length, 1);
  assert.equal(firstUndo.history.length, 1);

  const secondUndo = undoEditorSnapshot(firstUndo.history);
  assert.ok(secondUndo);
  assert.equal(secondUndo.snapshot.frames.length, 1);
  assert.equal(secondUndo.snapshot.placements.length, 0);
  assert.equal(secondUndo.history.length, 0);
});

test("undoEditorSnapshot returns null on an empty stack", () => {
  assert.equal(undoEditorSnapshot([]), null);
});

test("pushEditorSnapshot snapshots do not alias live arrays or adjust objects", () => {
  const frames = [fakeFrame("f1", null)];
  const placement = fakePlacement("placement-f1", "f1");
  const snapshot: EditorSnapshot = { frames, placements: [placement] };
  const history = pushEditorSnapshot([], snapshot);

  // 变更现值不影响已压入的快照。
  frames.push(fakeFrame("f2", 1));
  placement.cx = 999;
  placement.adjust.lengthScale = 2;

  const stored = history[0];
  assert.ok(stored);
  assert.equal(stored.frames.length, 1);
  assert.equal(stored.placements[0]?.cx, 10);
  assert.equal(stored.placements[0]?.adjust.lengthScale, 1);
});

test("shouldCoalesceHistory merges the same key inside the window only", () => {
  assert.equal(HISTORY_COALESCE_WINDOW_MS, 800);
  const key = "move:placement-f1";
  assert.equal(shouldCoalesceHistory(key, 1000, key, 1500), true);
  assert.equal(shouldCoalesceHistory(key, 1000, key, 1000 + 799), true);
  // 超窗（含边界 800ms）不合并。
  assert.equal(shouldCoalesceHistory(key, 1000, key, 1800), false);
  // 不同操作键不合并。
  assert.equal(shouldCoalesceHistory("move:a", 1000, "move:b", 1200), false);
  // 无上次记录不合并。
  assert.equal(shouldCoalesceHistory(null, 0, key, 1000), false);
});

// ── 导出分区与键盘微调辅助（§5.8 / §5.5） ──

test("partitionExportTextures splits by loaded textures and dedupes failed sources", () => {
  const loaded = new Set(["/tex/a.png"]);
  const placements: NailPlacement[] = [
    fakePlacement("p1", "f1"),
    fakePlacement("p2", "f2"),
    fakePlacement("p3", "f3"),
  ];
  placements[0]!.textureSrc = "/tex/a.png";
  placements[1]!.textureSrc = "/tex/broken.png";
  placements[2]!.textureSrc = "/tex/broken.png";

  const partition = partitionExportTextures(placements, (src) => loaded.has(src));
  assert.deepEqual(
    partition.ok.map((item) => item.id),
    ["p1"]
  );
  assert.deepEqual(
    partition.failed.map((item) => item.id),
    ["p2", "p3"]
  );
  // 两个贴合共用同一坏纹理 → 去重后只报一次。
  assert.deepEqual(partition.failedSources, ["/tex/broken.png"]);
});

test("partitionExportTextures returns everything ok when all textures are loaded", () => {
  const placements = [fakePlacement("p1", "f1")];
  const partition = partitionExportTextures(placements, () => true);
  assert.equal(partition.ok.length, 1);
  assert.equal(partition.failed.length, 0);
  assert.deepEqual(partition.failedSources, []);
});

test("NUDGE step constants stay at the 2px / Shift 8px contract", () => {
  assert.equal(NUDGE_STEP_PX, 2);
  assert.equal(NUDGE_STEP_LARGE_PX, 8);
});

test("clampToImageBounds clamps nudged coordinates to the image range", () => {
  assert.deepEqual(clampToImageBounds(-3, 12, 100, 200), { x: 0, y: 12 });
  assert.deepEqual(clampToImageBounds(50, 260, 100, 200), { x: 50, y: 200 });
  assert.deepEqual(clampToImageBounds(99, 199, 100, 200), { x: 99, y: 199 });
});

// ── 组件源码合同（node:test 无 DOM 渲染，按源码合同断言交互优先级/键盘/面板分支） ──

function readSource(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf8");
}

test("NailCanvas closes frame hit-testing while showFrames is false (preview mode)", () => {
  const source = readSource("../src/components/NailCanvas.tsx");
  assert.match(
    source,
    /if \(showFrames\) \{\s*const frameIndex = frameHitTest/,
    "预览模式下 frameHitTest 必须在 showFrames 守卫内（隐藏框后框不再可点）"
  );
  // 预览模式点空白 → onPlacementSelect(null) 取消选中仍保留。
  assert.match(source, /onPlacementSelect\(null\)/);
});

test("NailCanvas exposes keyboard-alternative props and a focusable canvas", () => {
  const source = readSource("../src/components/NailCanvas.tsx");
  assert.match(source, /tabIndex=\{0\}/);
  assert.match(source, /onPlacementNudge\?\(id: string, dx: number, dy: number\): void/);
  assert.match(source, /onPlacementDelete\?\(id: string\): void/);
  assert.match(source, /onFrameNudge\?\(id: string, dx: number, dy: number\): void/);
  assert.match(source, /onFrameDelete\?\(id: string\): void/);
  assert.match(source, /onExported\?\(result: \{ skipped: number \}\): void/);
  // Delete / Backspace 删除选中对象；方向键微调（Shift 加步长）。
  assert.match(source, /e\.key === "Delete" \|\| e\.key === "Backspace"/);
  assert.match(source, /e\.shiftKey \? NUDGE_STEP_LARGE_PX : NUDGE_STEP_PX/);
  assert.match(source, /onKeyDown=\{handleCanvasKeyDown\}/);
});

test("NailCanvas export flow gates on texture preload and offers retry / force / cancel", () => {
  const source = readSource("../src/components/NailCanvas.tsx");
  assert.match(source, /partitionExportTextures\(placements, isTextureLoaded\)/);
  assert.match(source, /preloadPlacementTextures/);
  assert.match(source, /个纹理无法加载，已暂停导出/);
  assert.match(source, /重试加载/);
  assert.match(source, /仍要导出/);
  assert.match(source, /已导出，但跳过 \$\{partition\.failed\.length\} 处贴合纹理/);
  // 导出成功后回调页面（skipped 数量）。
  assert.match(source, /onExported\?\.\(\{ skipped: placements\.length - targets\.length \}\)/);
});

test("TextureSetPicker is focusable with state-aware label and Enter/Escape toggling", () => {
  const source = readSource("../src/components/TextureSetPicker.tsx");
  assert.match(source, /role="group"/);
  // role=group 不支持 aria-expanded（jsx-a11y/role-supports-aria-props），
  // 展开状态经动态 aria-label 表达（已展开/已折叠）。
  assert.match(source, /aria-label=\{expanded \? `纹理套装：\$\{set\.name\}（已展开）` : `纹理套装：\$\{set\.name\}（已折叠）`\}/);
  assert.match(source, /tabIndex=\{0\}/);
  assert.match(source, /event\.key === "Enter"/);
  assert.match(source, /event\.key === "Escape" && expanded/);
  // 静止态两个明确动作；展开态单卡钉选保留 aria-pressed。
  assert.match(source, /选择这套/);
  assert.match(source, /查看单指/);
  assert.match(source, /aria-pressed=\{pinned \|\| undefined\}/);
});

test("TextureSetPicker no longer applies the set from stack clicks", () => {
  const source = readSource("../src/components/TextureSetPicker.tsx");
  // 点堆叠本体只切换展开态（移动端不直接应用套装）。
  assert.match(source, /点堆叠本体：静止态展开、展开态收起/);
  assert.match(source, /静止态点堆叠卡 = 展开（不直接应用套装）/);
  // 旧「点堆叠应用整套」直达按钮已被「选择这套」替代。
  assert.doesNotMatch(source, /应用整套/);
});

test("TextureSetPicker apply-all uses an inline two-step armed confirm", () => {
  const source = readSource("../src/components/TextureSetPicker.tsx");
  assert.match(source, /将当前套装应用到全部甲面/);
  assert.match(source, /确认替换 \$\{frameCount\} 个甲面/);
  assert.match(source, /APPLY_ALL_ARMED_MS = 5000/);
  // armed 说明：影响 N 个甲面框 + 已有贴合将被替换提示。
  assert.match(source, /将为 \{frameCount\} 个甲面框贴合/);
  assert.match(source, /已有贴合将被替换/);
  // 失焦与 Esc 取消 armed 态。
  assert.match(source, /onBlur=\{applyAllArmed \? disarmApplyAll : undefined\}/);
  assert.match(source, /event\.key === "Escape" && applyAllArmed/);
});

test("EditorObjectPanel renders per-selection branches and the object list", () => {
  const source = readSource("../src/components/EditorObjectPanel.tsx");
  // 三个状态分支：未选中引导 / 已贴合 / 未贴合。
  assert.match(source, /selection === null \?/);
  assert.match(source, /selection\.kind === "placement"/);
  assert.match(source, /已贴合/);
  assert.match(source, /未贴合/);
  assert.match(source, /替换为当前纹理/);
  assert.match(source, /微调/);
  assert.match(source, /删除贴合/);
  assert.match(source, /用当前纹理贴合/);
  assert.match(source, /删除甲面框/);
  // 对象列表：逐甲一行 button + ↑/↓ 焦点移动。
  assert.match(source, /甲面对象列表/);
  assert.match(source, /ArrowDown/);
  assert.match(source, /ArrowUp/);
  assert.match(source, /aria-current=\{selected \? "true" : undefined\}/);
});

test("editor page keeps the interaction priority and wires the object panel", () => {
  const source = readSource("../src/app/editor/page.tsx");
  // 点击贴合 → 选中并打开面板（对象面板以贴合优先）。
  assert.match(source, /if \(selectedPlacement\) \{[\s\S]*?kind: "placement"/);
  // 状态行「已贴合「套装 / 指名」」由页面派生。
  assert.match(source, /已贴合「/);
  // 替换为当前纹理动作接 handleFrameClick。
  assert.match(source, /onReplace=\{\(\) => \{/);
  assert.match(source, /void handleFrameClick\(frame\)/);
  // 手动框删除与识别框保护提示。
  assert.match(source, /识别得到的甲面框暂不支持删除/);
  assert.match(source, /frame-remove:\$\{id\}/);
  // 应用全部在页面侧执行（applySetToFrames）。
  assert.match(source, /applySetToFrames\(\{/);
  assert.match(source, /apply-all/);
});

test("editor page undo snapshot covers every documented operation key", () => {
  const source = readSource("../src/app/editor/page.tsx");
  // 模板键（`place: 等）只按前缀匹配，闭合括号由各调用点自行收尾。
  const requiredCalls = [
    'pushHistoryCoalesced("detect")',
    'pushHistoryCoalesced("matte-detect")',
    'pushHistoryCoalesced("matte-refine")',
    'pushHistoryCoalesced("frame-add")',
    "pushHistoryCoalesced(`frame-move:",
    "pushHistoryCoalesced(`frame-remove:",
    "pushHistoryCoalesced(`frame-finger:",
    "pushHistoryCoalesced(`place:",
    "pushHistoryCoalesced(`move:",
    "pushHistoryCoalesced(`adjust:",
    "pushHistoryCoalesced(`remove:",
    'pushHistoryCoalesced("reset")',
    'pushHistoryCoalesced("apply-all")',
  ];
  for (const call of requiredCalls) {
    assert.ok(source.includes(call), `撤销栈缺少操作键：${call}`);
  }
});

test("editor page registers global Ctrl/Cmd+Z undo that skips text inputs", () => {
  const source = readSource("../src/app/editor/page.tsx");
  assert.match(source, /event\.ctrlKey \|\| event\.metaKey/);
  assert.match(source, /target\.tagName === "INPUT"/);
  assert.match(source, /target\.isContentEditable/);
});

test("editor page keeps canvas stateless positioning (no business state in NailCanvas)", () => {
  const source = readSource("../src/components/NailCanvas.tsx");
  // NailCanvas 只允许纯 UI 局部 state（导出提示）；不得出现 frames/placements 的 useState。
  assert.doesNotMatch(source, /useState<NailPlacement/);
  assert.doesNotMatch(source, /useState<PlacementFrameInput/);
});

// ── 灵感款试戴路径（2026-11-03 用户指示）：图库选择弹层 + 编辑器自动贴合 ──

test("GalleryGrid look card opens the trial-mode chooser dialog", () => {
  const source = readSource("../src/components/GalleryGrid.tsx");
  // 卡片图与标题改为打开「试戴方式」选择弹层，不再是直达 /editor 的 Link。
  assert.match(source, /setChooser\(\{ id: String\(item\.id\), name: item\.name \}\)/);
  assert.match(source, /AppDialog/);
  // 弹层两个选项：静态试色（编辑器）与 AR 实时预览，均携带所选灵感款参数。
  assert.match(source, /上传手部照片 · 静态试色/);
  assert.match(source, /开启摄像头 · AR 实时预览/);
  assert.match(source, /\/editor\?gallery=\$\{chooser\.id\}/);
  assert.match(source, /\/ar-tryon\?gallery=\$\{chooser\.id\}/);
});

test("editor page auto-applies the inspiration set after nail detection", () => {
  const source = readSource("../src/app/editor/page.tsx");
  // 灵感款自动贴合：识别出甲面框且灵感色已映射相近套装时自动应用。
  assert.match(source, /applyInspirationSet/);
  assert.match(source, /inspirationAutoRef/);
  assert.match(source, /pushHistoryCoalesced\("inspiration-apply"\)/);
  // 每次上传至多自动应用一次；换图（resetEditState）重新武装。
  assert.match(source, /inspirationAppliedRef\.current = true/);
  assert.match(source, /inspirationAppliedRef\.current = false/);
  // 识别成功写入 frames 后立即尝试自动贴合（framesRef 同步赋值保证同轮可见）。
  assert.match(
    source,
    /framesRef\.current = regions;[\s\S]{0,600}?inspirationAutoRef\.current\)/,
    "识别完成后必须立即尝试灵感自动贴合"
  );
});
