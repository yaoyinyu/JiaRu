import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "audit-development-cycle-015-historical-mask-candidates.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('audit',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['audit']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("历史候选只覆盖15个定位槽位且不能直接批准mask", () => {
  const result = evaluate(["print(json.dumps({'file':m.EXPECTED_FILE,'masks':m.EXPECTED_MASKS,'approved':0}))"]);
  assert.equal(result.file, "nail_01063_69417639000000001f005854_0.jpg");
  assert.equal(result.masks, 15);
  assert.equal(result.approved, 0);
});

test("几何通过数量不能代替逐甲终审", () => {
  const result = evaluate(["print(json.dumps({'geometryPassDoesNotApproveMask':True,'originalResolutionReviewRequired':True}))"]);
  assert.equal(result.geometryPassDoesNotApproveMask, true);
  assert.equal(result.originalResolutionReviewRequired, true);
});
