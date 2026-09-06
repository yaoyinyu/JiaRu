import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { auditReleaseProgress, CURRENT_RELEASE_REQUIREMENTS } from "../scripts/lib/nail-texture-release-progress.ts";

const fixture = () => CURRENT_RELEASE_REQUIREMENTS.map((id) => ({ id, task: id, status: "✅ PASS",
  evidence: "lifecycle=closed; outcome=pass; gateRole=current-release; required=true" }));

test("当前真实进度文档只选择七项发布要求且审计基础设施一项通过", () => {
  const text = readFileSync("docs/nail-texture-local-inference-implementation-progress.md", "utf8");
  const rows = [...text.matchAll(/^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$/gm)]
    .map((m) => ({ id: m[1]!.trim(), task: m[2]!.trim(), status: m[3]!.trim(), evidence: m[4]!.trim() }));
  const result = auditReleaseProgress(rows);
  assert.deepEqual(result.errors, []);
  assert.equal(result.currentRequirementCount, 7);
  assert.equal(result.passMarkerCount, 1);
  assert.equal(result.incompleteMarkers.length, 6);
  assert.ok(result.historicalMarkerCount >= 523);
  assert.equal(result.ok, false);
});

test("历史失败保留原文且不阻断全部通过的当前要求", () => {
  const history = { id: "CANDIDATE57", task: "test", status: "❌ TEST HOLD", evidence: "13%漏甲" };
  const report = auditReleaseProgress([...fixture(), history]);
  assert.equal(report.ok, true);
  assert.equal(report.historicalMarkerCount, 1);
  assert.equal(report.records.at(-1)?.status, history.status);
  assert.equal(report.records.at(-1)?.outcome, "legacy-unclassified");
});
test("删除、降级、重复或不完整声明均被拒绝", () => {
  assert.equal(auditReleaseProgress(fixture().slice(1)).ok, false);
  for (const evidence of ["", "lifecycle=closed; outcome=pass; gateRole=historical; required=false",
    "lifecycle=closed; outcome=pass; gateRole=current-release; required=true; outcome=hold"] ) {
    const rows = fixture(); rows[0]!.evidence = evidence;
    assert.equal(auditReleaseProgress(rows).ok, false);
  }
  assert.equal(auditReleaseProgress([...fixture(), fixture()[0]!]).ok, false);
});
test("生命周期完成不能把质量拒绝改成通过", () => {
  const rows = fixture(); rows[0]!.status = "✅ PASS（候选拒绝）";
  assert.equal(auditReleaseProgress(rows).ok, false);
  rows[0]!.evidence = "lifecycle=closed; outcome=rejected; gateRole=current-release; required=true";
  assert.equal(auditReleaseProgress(rows).incompleteMarkers.length, 1);
});
