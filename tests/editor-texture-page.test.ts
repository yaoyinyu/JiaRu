import assert from "node:assert/strict";
import test from "node:test";

import {
  applyRefinedFrameMasks,
  buildManualFrame,
  firstUnoccupiedFinger,
  frameToMatteCandidate,
  MISSING_FINGER_HINT,
  NO_SELECTION_HINT,
  parsePinnedTextureKey,
  pushPlacementHistory,
  replacePlacementForFrame,
  resolveActiveTexture,
  textureKeyFor,
  undoPlacementHistory,
} from "../src/lib/editor-texture-state.ts";
import {
  closestTextureSet,
  NAIL_TEXTURE_SETS,
  textureSrcFor,
  type NailTextureSet,
} from "../src/lib/nail-texture-sets.ts";

const FIXTURE_SETS: readonly NailTextureSet[] = [
  {
    id: "set-a",
    name: "套装A",
    source: "测试",
    dominantColor: "#FF0000",
    textures: [
      { finger: 0, src: "/nail-textures/set-a/finger-1.png" },
      { finger: 2, src: "/nail-textures/set-a/finger-3.png" },
    ],
  },
  {
    id: "set-b",
    name: "套装B",
    source: "测试",
    dominantColor: "#0000FF",
    textures: [
      { finger: 1, src: "/nail-textures/set-b/finger-2.png" },
      { finger: 4, src: "/nail-textures/set-b/finger-5.png" },
    ],
  },
];

// ── 钉选键解析 ──

test("parsePinnedTextureKey round-trips valid keys", () => {
  const key = textureKeyFor("set-a", 3);
  assert.equal(key, "set-a/3");
  assert.deepEqual(parsePinnedTextureKey(key), { setId: "set-a", finger: 3 });
});

test("parsePinnedTextureKey rejects malformed keys", () => {
  assert.equal(parsePinnedTextureKey(null), null);
  assert.equal(parsePinnedTextureKey(undefined), null);
  assert.equal(parsePinnedTextureKey(""), null);
  assert.equal(parsePinnedTextureKey("set-a"), null);
  assert.equal(parsePinnedTextureKey("/3"), null);
  assert.equal(parsePinnedTextureKey("set-a/"), null);
  assert.equal(parsePinnedTextureKey("set-a/5"), null);
  assert.equal(parsePinnedTextureKey("set-a/-1"), null);
  assert.equal(parsePinnedTextureKey("set-a/x"), null);
});

// ── activeTexture 解析：钉选优先 / 套装指位匹配 / 缺失分支 ──

test("resolveActiveTexture prefers pinned texture over set matching", () => {
  const resolution = resolveActiveTexture({
    sets: FIXTURE_SETS,
    pinnedTextureKey: "set-b/1",
    activeSetId: "set-a",
    finger: 0,
  });
  assert.equal(resolution.status, "pinned");
  assert.equal(resolution.texture?.src, "/nail-textures/set-b/finger-2.png");
  assert.equal(resolution.texture?.key, "set-b/1");
});

test("resolveActiveTexture falls back to set finger texture", () => {
  const resolution = resolveActiveTexture({
    sets: FIXTURE_SETS,
    pinnedTextureKey: null,
    activeSetId: "set-a",
    finger: 2,
  });
  assert.equal(resolution.status, "set");
  assert.equal(resolution.texture?.src, "/nail-textures/set-a/finger-3.png");
  assert.equal(resolution.texture?.key, "set-a/2");
});

test("resolveActiveTexture falls back to set when pinned target vanished", () => {
  const resolution = resolveActiveTexture({
    sets: FIXTURE_SETS,
    pinnedTextureKey: "missing-set/0",
    activeSetId: "set-a",
    finger: 0,
  });
  assert.equal(resolution.status, "set");
  assert.equal(resolution.texture?.setId, "set-a");
});

test("resolveActiveTexture reports missing when finger is null", () => {
  const resolution = resolveActiveTexture({
    sets: FIXTURE_SETS,
    pinnedTextureKey: null,
    activeSetId: "set-a",
    finger: null,
  });
  assert.equal(resolution.status, "missing");
  assert.equal(resolution.texture, null);
  assert.equal(resolution.message, MISSING_FINGER_HINT);
});

test("resolveActiveTexture reports missing when the finger has no texture", () => {
  const resolution = resolveActiveTexture({
    sets: FIXTURE_SETS,
    pinnedTextureKey: null,
    activeSetId: "set-a",
    finger: 1,
  });
  assert.equal(resolution.status, "missing");
  assert.equal(resolution.message, MISSING_FINGER_HINT);
});

test("resolveActiveTexture reports missing when nothing is selected", () => {
  const resolution = resolveActiveTexture({
    sets: FIXTURE_SETS,
    pinnedTextureKey: null,
    activeSetId: null,
    finger: 0,
  });
  assert.equal(resolution.status, "missing");
  assert.equal(resolution.message, NO_SELECTION_HINT);
});

// ── placement 替换：同 frame 重贴先移除旧贴合 ──

interface FakePlacement {
  id: string;
  frameId: string;
  label: string;
}

const FAKE_PLACEMENTS: readonly FakePlacement[] = [
  { id: "p1", frameId: "frame-1", label: "old-1" },
  { id: "p2", frameId: "frame-2", label: "keep-2" },
];

test("replacePlacementForFrame removes the previous placement of the same frame", () => {
  const next: FakePlacement = { id: "p3", frameId: "frame-1", label: "new-1" };
  const result = replacePlacementForFrame(FAKE_PLACEMENTS, next);
  assert.equal(result.length, 2);
  assert.deepEqual(
    result.find((item) => item.frameId === "frame-1"),
    next
  );
  assert.ok(result.some((item) => item.label === "keep-2"));
  assert.ok(!result.some((item) => item.label === "old-1"));
});

test("replacePlacementForFrame appends when the frame has no placement yet", () => {
  const next: FakePlacement = { id: "p4", frameId: "frame-9", label: "new-9" };
  const result = replacePlacementForFrame(FAKE_PLACEMENTS, next);
  assert.equal(result.length, 3);
  assert.equal(result[result.length - 1]?.frameId, "frame-9");
});

// ── history 撤销栈 ──

test("pushPlacementHistory snapshots the current list without aliasing", () => {
  const current: FakePlacement[] = [...FAKE_PLACEMENTS];
  const history = pushPlacementHistory([], current);
  assert.equal(history.length, 1);
  current.push({ id: "px", frameId: "x", label: "later" });
  // 快照是浅拷贝：之后对原数组的追加不影响历史。
  assert.equal(history[0]?.length, 2);
});

test("undoPlacementHistory pops the last snapshot and keeps the rest", () => {
  const snapshotA: FakePlacement[] = [{ id: "p1", frameId: "frame-1", label: "a" }];
  const snapshotB: FakePlacement[] = [
    { id: "p1", frameId: "frame-1", label: "a" },
    { id: "p2", frameId: "frame-2", label: "b" },
  ];
  const history = [snapshotA, snapshotB];
  const result = undoPlacementHistory(history);
  assert.ok(result);
  assert.equal(result.placements.length, 2);
  assert.equal(result.history.length, 1);

  const again = undoPlacementHistory(result.history);
  assert.ok(again);
  assert.equal(again.placements.length, 1);
  assert.equal(again.history.length, 0);
});

test("undoPlacementHistory returns null on an empty stack", () => {
  assert.equal(undoPlacementHistory([]), null);
});

// ── 手动甲面框 ──

test("buildManualFrame clamps size to 42-120 / 28-72 and picks the first free finger", () => {
  const frame = buildManualFrame({
    id: "manual-1",
    x: 500,
    y: 600,
    imageWidth: 2000,
    imageHeight: 1000,
    occupiedFingers: [0, 1],
  });
  // 最长边 2000 → 长 200 → 钳制 120；宽 120*0.58=69.6→70（28-72 内）。
  assert.equal(frame.nl, 120);
  assert.equal(frame.nw, 70);
  assert.equal(frame.angle, 0);
  assert.equal(frame.assignedFinger, 2);
  assert.ok(frame.cx >= frame.nw / 2 && frame.cx <= 2000 - frame.nw / 2);
  assert.ok(frame.cy >= frame.nl / 2 && frame.cy <= 1000 - frame.nl / 2);
});

test("buildManualFrame uses 10% of the longest edge for small images", () => {
  const frame = buildManualFrame({
    id: "manual-2",
    x: 100,
    y: 100,
    imageWidth: 640,
    imageHeight: 480,
    occupiedFingers: [],
  });
  // 最长边 640 → 长 64；宽 64*0.58=37.12→37。
  assert.equal(frame.nl, 64);
  assert.equal(frame.nw, 37);
  assert.equal(frame.assignedFinger, 0);
});

test("buildManualFrame returns null finger when all five are taken", () => {
  const frame = buildManualFrame({
    id: "manual-3",
    x: 100,
    y: 100,
    imageWidth: 800,
    imageHeight: 800,
    occupiedFingers: [0, 1, 2, 3, 4],
  });
  assert.equal(frame.assignedFinger, null);
});

test("firstUnoccupiedFinger skips taken fingers and returns null when full", () => {
  assert.equal(firstUnoccupiedFinger([0, 1, 3]), 2);
  assert.equal(firstUnoccupiedFinger([null, null]), 0);
  assert.equal(firstUnoccupiedFinger([0, 1, 2, 3, 4]), null);
});

// ── 精细抠图回填 ──

test("frameToMatteCandidate maps frame geometry to candidate fields", () => {
  const candidate = frameToMatteCandidate({
    id: "nail-1",
    cx: 10,
    cy: 20,
    angle: 0.5,
    nl: 80,
    nw: 40,
    assignedFinger: 2,
    confidence: "medium",
    source: "mediapipe",
    warnings: ["angle_stabilized_from_group"],
  });
  assert.equal(candidate.id, "nail-1");
  assert.equal(candidate.cx, 10);
  assert.equal(candidate.cy, 20);
  assert.equal(candidate.length, 80);
  assert.equal(candidate.width, 40);
  assert.equal(candidate.angle, 0.5);
  assert.equal(candidate.confidence, "medium");
  assert.equal(candidate.source, "mediapipe");
  assert.equal(candidate.suggestedFinger, 2);
  assert.deepEqual(candidate.warnings, ["angle_stabilized_from_group"]);
});

test("frameToMatteCandidate defaults to manual low confidence", () => {
  const candidate = frameToMatteCandidate({
    id: "nail-2",
    cx: 0,
    cy: 0,
    angle: 0,
    nl: 50,
    nw: 30,
    assignedFinger: null,
  });
  assert.equal(candidate.confidence, "low");
  assert.equal(candidate.source, "manual");
  assert.equal(candidate.suggestedFinger, null);
});

test("applyRefinedFrameMasks replaces masks and recomputes geometry", () => {
  const frames = [
    { id: "a", cx: 1, cy: 2, nl: 30, nw: 20, mask: undefined },
    { id: "b", cx: 3, cy: 4, nl: 50, nw: 25, mask: undefined },
  ];
  const masks = new Map<string, object>([["a", { width: 8 }]]);
  const result = applyRefinedFrameMasks(frames, masks, (frame) => {
    if (frame.id === "a") return { cx: 11, cy: 22, length: 90, width: 45 };
    return null;
  });
  assert.equal(result[0]?.mask, masks.get("a"));
  assert.equal(result[0]?.cx, 11);
  assert.equal(result[0]?.cy, 22);
  assert.equal(result[0]?.nl, 90);
  assert.equal(result[0]?.nw, 45);
  // mask 有值但几何为 null → 保留原几何。
  assert.equal(result[1]?.cx, 3);
  assert.equal(result[1]?.cy, 4);
  assert.equal(result[1]?.nl, 50);
});

test("applyRefinedFrameMasks keeps frames without a refined mask untouched", () => {
  const frames = [
    { id: "a", cx: 1, cy: 2, nl: 30, nw: 20 },
    { id: "b", cx: 3, cy: 4, nl: 50, nw: 25 },
  ];
  const result = applyRefinedFrameMasks(frames, new Map(), () => ({
    cx: 99,
    cy: 99,
    length: 99,
    width: 99,
  }));
  assert.deepEqual(result, frames);
});

// ── ?preset= 色 → closestTextureSet 映射存在性 ──

test("closestTextureSet maps a valid hex to the nearest set and nulls invalid hex", () => {
  // v1.2.178 起清单已登记 5 套真实纹理套装：合法 hex 返回最接近主色的套装。
  const coral = closestTextureSet("#F88379");
  assert.ok(coral, "合法 hex 应命中套装而非 null");
  assert.ok(NAIL_TEXTURE_SETS.some((item) => item.id === coral!.id));
  assert.equal(closestTextureSet("not-a-color"), null);
});

test("textureSrcFor misses missing fingers and hits registered ones", () => {
  const set = FIXTURE_SETS[0];
  assert.ok(set);
  assert.equal(textureSrcFor(set, 0)?.src, "/nail-textures/set-a/finger-1.png");
  assert.equal(textureSrcFor(set, 4), null);
});
