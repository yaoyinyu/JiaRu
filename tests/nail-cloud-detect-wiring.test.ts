import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// ── 云端识别接线源码合同（v1.2.217）：三站共享切换组件与判决入口 ──

function readSource(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf8");
}

test("shared mode switch renders local/cloud chips with consent dialog", () => {
  const source = readSource("../src/components/NailDetectModeSwitch.tsx");
  assert.match(source, /aria-pressed=\{mode === "local"\}/);
  assert.match(source, /aria-pressed=\{mode === "cloud"\}/);
  // 一次性隐私确认弹层（AppDialog）+ 同意后回调。
  assert.match(source, /云端识别隐私说明/);
  assert.match(source, /onConsentGranted/);
  assert.match(source, /同意并使用云端识别/);
  // 云端不可用时 chip 禁用并说明原因。
  assert.match(source, /云端识别未配置/);
});

test("editor page wires the mode switch with mode-aware detection branching", () => {
  const source = readSource("../src/app/editor/page.tsx");
  assert.match(source, /NailDetectModeSwitch/);
  assert.match(source, /decideNailDetectRun/);
  // 模式分流经 ref（不得把模式状态并入识别 effect 依赖）。
  assert.match(source, /detectModeRef\.current\.mode === "cloud"/);
  assert.match(source, /runCloudDetectRef/);
  // 云端识别独立撤销栈键与 0 候选提示。
  assert.match(source, /pushHistoryCoalesced\("cloud-detect"\)/);
  assert.match(source, /云端未识别到甲面/);
  // 降级文案映射。
  assert.match(source, /cloudDetectMessageFromReason/);
  // 换图/卸载时中止云端请求。
  assert.match(source, /cloudAbortRef\.current\?\.abort\(\)/);
});

// ── /nail-analysis 个性化分析页接线（v1.2.216）：上传事件分流，云端候选免 remap ──

test("nail-analysis page renders the shared detect mode switch", () => {
  const source = readSource("../src/app/nail-analysis/page.tsx");
  assert.match(source, /NailDetectModeSwitch/);
  assert.match(source, /useNailDetectMode\(\)/);
  // 识别进行中禁用切换。
  assert.match(source, /disabled=\{stage === "analyzing"\}/);
  // 一次性隐私确认由共享 hook 落库。
  assert.match(source, /onConsentGranted=\{detectMode\.acknowledgeCloudConsent\}/);
});

test("nail-analysis page gates cloud runs through decideNailDetectRun", () => {
  const source = readSource("../src/app/nail-analysis/page.tsx");
  assert.match(source, /decideNailDetectRun\(/);
  // 两个云端后端按所选 backend 分流。
  assert.match(source, /detectNailsWithArk\(/);
  assert.match(source, /detectNailsWithCloudMatte\(/);
  // 降级文案走共享映射，而非页面自造。
  assert.match(source, /cloudDetectMessageFromReason\(/);
});

test("nail-analysis cloud path skips remap and reuses the shared capture/analyze path", () => {
  const source = readSource("../src/app/nail-analysis/page.tsx");
  // 云端候选已是原图像素坐标：云端分支内不得再走 remap。
  const cloudBranch = source.match(/if \(cloudMode\) \{[\s\S]*?\n\s*\} else \{/);
  assert.ok(cloudBranch, "缺少云端识别分支");
  assert.doesNotMatch(cloudBranch[0], /remapNailTextureCandidatesToOriginal/);
  // 本地路径仍保留 remap（降采样识别结果回原图坐标）。
  assert.match(source, /candidates = remapNailTextureCandidatesToOriginal\(/);
  // 云端与本地汇合同一处 capture（同一 analyze 后处理）。
  assert.match(source, /setCapture\(\{[\s\S]*?candidates,[\s\S]*?backend,\s*\}\);/);
});

test("nail-analysis page keeps auxiliary framing for cloud results", () => {
  const source = readSource("../src/app/nail-analysis/page.tsx");
  // 云端 0 候选提示（0 候选不产出任何推荐口径）。
  assert.match(source, /云端未识别到甲面，未产出推荐/);
  // 云端成功提示保持辅助定位口径，不得表述为自动分析成功。
  assert.match(source, /已按辅助定位处理，结果仅供参考/);
  // 云端 capture 走 fallback，琥珀辅助声明（present.ts auxiliaryAnalysisNotice）页面级常显。
  assert.match(source, /let backend: Capture\["backend"\] = "fallback";/);
});

test("nail-analysis page aborts cloud requests on reset and unmount", () => {
  const source = readSource("../src/app/nail-analysis/page.tsx");
  // 复用页面现有 abort ref：reset 与卸载均中止（覆盖云端 fetch signal）。
  assert.match(source, /abortRef\.current\?\.abort\(\)/);
  // 云端识别请求携带同一 abort signal。
  assert.match(source, /runCloudDetect\(\{ bitmap, signal: abort\.signal \}\)/);
  // 中止后不得把取消当作失败提示回写状态。
  assert.match(source, /if \(options\.signal\.aborted\) return null;/);
});

// ── /ar-tryon NailArtPicker 接线（v1.2.216）：上传级联分流 + 云端候选进选择器 ──

test("ar picker wires the mode switch with cloud-first detection branching", () => {
  const source = readSource("../src/components/NailArtPicker.tsx");
  assert.match(source, /NailDetectModeSwitch/);
  assert.match(source, /decideNailDetectRun/);
  // 模式分流经 ref（不得把模式状态并入识别 effect 依赖）。
  assert.match(source, /detectModeRef\.current\.mode === "cloud"/);
  assert.match(source, /runCloudDetectRef/);
  // 云端 0 候选提示（保留当前结果，不静默兜底）。
  assert.match(source, /云端未识别到甲面，已保留当前结果；可切换本地或手动添加/);
  // 降级文案映射与云端请求中止（跳过识别/换图/卸载）。
  assert.match(source, /cloudDetectMessageFromReason/);
  assert.match(source, /cloudAbortRef\.current\?\.abort\(\)/);
});
