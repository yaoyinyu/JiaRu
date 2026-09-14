import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "audit-development-cycle-015-generated-intake.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('intake',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['intake']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("首批3张通过后133张活动目标还剩130张", () => {
  const result = evaluate(["print(json.dumps({'target':m.TARGET_SOURCE_QUALIFIED,'frozen':3,'remaining':m.TARGET_SOURCE_QUALIFIED-3,'decision':m.decision_for_count(3),'next':m.next_action_for_count(3)}))"]);
  assert.equal(result.target, 133);
  assert.equal(result.frozen, 3);
  assert.equal(result.remaining, 130);
  assert.equal(result.decision, "freeze_3_new_source_qualified_candidates_continue_to_133");
  assert.equal(result.next, "generate_review_and_freeze_next_10_source_qualified_candidates_to_reach_13_of_133");
});

test("累计7张通过后只需再冻结6张即可到13张检查点", () => {
  const result = evaluate(["print(json.dumps({'frozen':7,'remaining':m.TARGET_SOURCE_QUALIFIED-7,'decision':m.decision_for_count(7),'next':m.next_action_for_count(7)}))"]);
  assert.equal(result.frozen, 7);
  assert.equal(result.remaining, 126);
  assert.equal(result.decision, "freeze_7_cumulative_source_qualified_candidates_continue_to_133");
  assert.equal(result.next, "generate_review_and_freeze_next_6_source_qualified_candidates_to_reach_13_of_133");
});

test("累计13张通过后进入下一批10张滚动检查点", () => {
  const result = evaluate(["print(json.dumps({'frozen':13,'remaining':m.TARGET_SOURCE_QUALIFIED-13,'decision':m.decision_for_count(13),'next':m.next_action_for_count(13)}))"]);
  assert.equal(result.frozen, 13);
  assert.equal(result.remaining, 120);
  assert.equal(result.decision, "freeze_13_cumulative_source_qualified_candidates_continue_to_133");
  assert.equal(result.next, "generate_review_and_freeze_next_10_source_qualified_candidates_to_reach_23_of_133");
});

test("源图门撤销一张后先补1张恢复13张检查点", () => {
  const result = evaluate(["print(json.dumps({'next':m.next_action_for_count(12)}))"]);
  assert.equal(result.next, "generate_review_and_freeze_next_1_source_qualified_candidates_to_reach_13_of_133");
});

test("身份比较同时保留文件名哈希和来源组", () => {
  const result = evaluate(["r={'fileName':'A.PNG','imageSha256':'a'*64,'sourceGroup':'g1'}", "print(json.dumps(dict(zip(['fileName','imageSha256','sourceGroup'],m.identity(r,'x')))))"]);
  assert.deepEqual(result, { fileName: "a.png", imageSha256: "a".repeat(64), sourceGroup: "g1" });
});

test("前序冻结计数纠正只允许修改已登记的fullyVisibleNails", () => {
  const result = evaluate([
    "prior=[{'fileName':'two-hands.png','fullyVisibleNails':10,'sha256':'a'}]",
    "current=[{'fileName':'two-hands.png','fullyVisibleNails':8,'sha256':'a'}]",
    "corrections=[{'fileName':'two-hands.png','field':'fullyVisibleNails','oldValue':10,'newValue':8,'reason':'only eight visible'}]",
    "m.validate_prior_corrections(prior,current,corrections)",
    "print(json.dumps({'ok':True}))",
  ]);
  assert.equal(result.ok, true);
});

test("原分辨率发现解剖异常时显式撤销旧source pass", () => {
  const result = evaluate([
    "prior=[{'fileName':'bad.png','fullyVisibleNails':5,'sourceGateDecision':'pass','originalResolutionChecks':{'anatomyPlausible':True}}]",
    "current=[{'fileName':'bad.png','fullyVisibleNails':5,'sourceGateDecision':'exclude','originalResolutionChecks':{'anatomyPlausible':False},'exclusionReason':'six fingers'}]",
    "exclusions=[{'fileName':'bad.png','oldSourceGateDecision':'pass','newSourceGateDecision':'exclude','reason':'six fingers'}]",
    "m.validate_prior_corrections(prior,current,[],exclusions)",
    "print(json.dumps({'ok':True}))",
  ]);
  assert.equal(result.ok, true);
});
