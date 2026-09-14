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

test("身份比较同时保留文件名哈希和来源组", () => {
  const result = evaluate(["r={'fileName':'A.PNG','imageSha256':'a'*64,'sourceGroup':'g1'}", "print(json.dumps(dict(zip(['fileName','imageSha256','sourceGroup'],m.identity(r,'x')))))"]);
  assert.deepEqual(result, { fileName: "a.png", imageSha256: "a".repeat(64), sourceGroup: "g1" });
});
