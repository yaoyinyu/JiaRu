import assert from "node:assert/strict";
import test from "node:test";

import {
  boxIou,
  candidateBounds,
  instanceCenterInsideCandidate,
  matchMasksByIou,
  matchMasksToCandidates,
  rotatedRectBounds,
  type Box,
} from "../src/lib/nail-texture-recognition/mask-matching.ts";

test("boxIou：同一框为 1，不相交为 0，半重叠符合交并比", () => {
  const a: Box = [0, 0, 10, 10];
  assert.equal(boxIou(a, [0, 0, 10, 10]), 1);
  assert.equal(boxIou(a, [20, 20, 30, 30]), 0);
  // 交集 50，并集 150
  assert.ok(Math.abs(boxIou(a, [5, 0, 15, 10]) - 50 / 150) < 1e-12);
});

test("rotatedRectBounds：0° 与 90° 的长短轴互换", () => {
  assert.deepEqual(rotatedRectBounds(50, 50, 40, 20, 0), [30, 40, 70, 60]);
  const rotated = rotatedRectBounds(50, 50, 40, 20, Math.PI / 2);
  assert.ok(Math.abs(rotated[0] - 40) < 1e-9);
  assert.ok(Math.abs(rotated[1] - 30) < 1e-9);
  assert.ok(Math.abs(rotated[2] - 60) < 1e-9);
  assert.ok(Math.abs(rotated[3] - 70) < 1e-9);
});

test("candidateBounds 与旋转外接框一致", () => {
  const bounds = candidateBounds({
    id: "c1",
    cx: 100,
    cy: 80,
    length: 40,
    width: 20,
    angle: 0,
    score: 0.5,
    confidence: "low",
    source: "mediapipe",
    suggestedFinger: null,
  });
  assert.deepEqual(bounds, [80, 70, 120, 90]);
});

test("贪心一一匹配：高 IoU 先占用，实例不得复用", () => {
  const candidates = [
    { id: "a", box: [0, 0, 100, 100] as Box },
    { id: "b", box: [10, 0, 110, 100] as Box },
  ];
  const instances = [
    { index: 5, box: [0, 0, 100, 100] as Box },
    { index: 7, box: [10, 0, 110, 100] as Box },
  ];

  const result = matchMasksByIou(candidates, instances, 0.3);
  assert.equal(result.matches.length, 2);
  const byCandidate = new Map(result.matches.map((match) => [match.candidateId, match.instanceIndex]));
  assert.equal(byCandidate.get("a"), 5);
  assert.equal(byCandidate.get("b"), 7);
  assert.deepEqual(result.unmatchedCandidateIds, []);
  assert.deepEqual(result.unmatchedInstanceIndexes, []);
});

test("竞争同一实例时只保留一个匹配，另一候选进入未匹配", () => {
  const candidates = [
    { id: "a", box: [0, 0, 100, 100] as Box },
    { id: "b", box: [5, 5, 105, 105] as Box },
  ];
  const instances = [{ index: 0, box: [0, 0, 100, 100] as Box }];

  const result = matchMasksByIou(candidates, instances, 0.3);
  assert.equal(result.matches.length, 1);
  assert.equal(result.matches[0].candidateId, "a");
  assert.deepEqual(result.unmatchedCandidateIds, ["b"]);
});

test("输入顺序无关：实例乱序不改变匹配结果", () => {
  const candidates = [
    { id: "a", box: [0, 0, 100, 100] as Box },
    { id: "b", box: [200, 0, 300, 100] as Box },
  ];
  const forward = matchMasksByIou(candidates, [
    { index: 1, box: [0, 0, 100, 100] as Box },
    { index: 2, box: [200, 0, 300, 100] as Box },
  ]);
  const reversed = matchMasksByIou(candidates, [
    { index: 2, box: [200, 0, 300, 100] as Box },
    { index: 1, box: [0, 0, 100, 100] as Box },
  ]);

  const normalize = (result: typeof forward) =>
    result.matches
      .map((match) => `${match.candidateId}:${match.instanceIndex}`)
      .sort();
  assert.deepEqual(normalize(forward), normalize(reversed));
});

test("阈值以下不匹配；空实例返回全部未匹配", () => {
  const candidates = [{ id: "a", box: [0, 0, 100, 100] as Box }];
  const result = matchMasksByIou(candidates, [{ index: 0, box: [90, 90, 190, 190] as Box }], 0.5);
  assert.equal(result.matches.length, 0);
  assert.deepEqual(result.unmatchedCandidateIds, ["a"]);
  assert.deepEqual(result.unmatchedInstanceIndexes, [0]);

  const empty = matchMasksByIou(candidates, []);
  assert.equal(empty.matches.length, 0);
  assert.deepEqual(empty.unmatchedCandidateIds, ["a"]);
});

test("instanceCenterInsideCandidate：中心在内为真，外扩范围内仍为真，远处为假", () => {
  const candidate: Box = [0, 0, 100, 100];
  assert.equal(instanceCenterInsideCandidate([40, 40, 60, 60], candidate), true);
  // 中心 x = -8：超出框外 8px，外扩 0.15*100 = 15px 内
  assert.equal(instanceCenterInsideCandidate([-28, 40, 12, 60], candidate), true);
  // 中心 x = -20：超出外扩范围
  assert.equal(instanceCenterInsideCandidate([-50, 40, 10, 60], candidate), false);
  // padding = 0 时不外扩
  assert.equal(instanceCenterInsideCandidate([-28, 40, 12, 60], candidate, 0), false);
});

test("matchMasksToCandidates：中心命中优先，IoU 低于阈值也能匹配", () => {
  // 候选框比上游甲面框松得多：IoU 仅 0.04，但上游实例中心在候选内
  const candidates = [{ id: "c1", box: [0, 0, 200, 200] as Box }];
  const instances = [{ index: 3, box: [80, 80, 120, 120] as Box }];
  const result = matchMasksToCandidates(candidates, instances);

  assert.equal(result.matches.length, 1);
  assert.equal(result.matches[0].candidateId, "c1");
  assert.equal(result.matches[0].instanceIndex, 3);
  assert.equal(result.matches[0].reason, "center");
  assert.ok(result.matches[0].iou < 0.15);
  assert.deepEqual(result.unmatchedCandidateIds, []);
  assert.deepEqual(result.unmatchedInstanceIndexes, []);
});

test("matchMasksToCandidates：中心不在框内时退回 IoU 兜底，低于兜底阈值不匹配", () => {
  const candidate: Box = [70, 0, 170, 100];
  // IoU = 3000 / 17000 ≈ 0.176，但实例中心 x=50 落在候选外扩下界 55 之外
  const fallback = matchMasksToCandidates([{ id: "c1", box: candidate }], [
    { index: 0, box: [0, 0, 100, 100] as Box },
  ]);
  assert.equal(fallback.matches.length, 1);
  assert.equal(fallback.matches[0].reason, "iou");
  assert.ok(Math.abs(fallback.matches[0].iou - 3000 / 17000) < 1e-12);

  // 同一几何，抬高兜底阈值即不再匹配
  const strict = matchMasksToCandidates(
    [{ id: "c1", box: candidate }],
    [{ index: 0, box: [0, 0, 100, 100] as Box }],
    { minIou: 0.3 }
  );
  assert.equal(strict.matches.length, 0);
  assert.deepEqual(strict.unmatchedCandidateIds, ["c1"]);
  assert.deepEqual(strict.unmatchedInstanceIndexes, [0]);
});

test("matchMasksToCandidates：一一匹配，竞争同一实例的另一候选保持未匹配", () => {
  const candidates = [
    { id: "a", box: [0, 0, 100, 100] as Box },
    { id: "b", box: [0, 0, 100, 100] as Box },
  ];
  const instances = [{ index: 0, box: [40, 40, 60, 60] as Box }];
  const result = matchMasksToCandidates(candidates, instances);

  assert.equal(result.matches.length, 1);
  assert.equal(result.matches[0].candidateId, "a");
  assert.deepEqual(result.unmatchedCandidateIds, ["b"]);
});

test("matchMasksToCandidates：输入顺序无关且结果稳定", () => {
  const candidates = [
    { id: "a", box: [0, 0, 100, 100] as Box },
    { id: "b", box: [300, 0, 400, 100] as Box },
  ];
  const forward = matchMasksToCandidates(candidates, [
    { index: 1, box: [20, 20, 80, 80] as Box },
    { index: 2, box: [320, 20, 380, 80] as Box },
  ]);
  const reversed = matchMasksToCandidates(candidates, [
    { index: 2, box: [320, 20, 380, 80] as Box },
    { index: 1, box: [20, 20, 80, 80] as Box },
  ]);

  const normalize = (result: typeof forward) =>
    result.matches.map((match) => `${match.candidateId}:${match.instanceIndex}`).sort();
  assert.deepEqual(normalize(forward), normalize(reversed));
  assert.deepEqual(forward.unmatchedCandidateIds, []);
  assert.deepEqual(forward.unmatchedInstanceIndexes, []);
});

test("matchMasksToCandidates：空实例返回全部候选未匹配", () => {
  const result = matchMasksToCandidates([{ id: "a", box: [0, 0, 10, 10] as Box }], []);
  assert.equal(result.matches.length, 0);
  assert.deepEqual(result.unmatchedCandidateIds, ["a"]);
  assert.deepEqual(result.unmatchedInstanceIndexes, []);
});
