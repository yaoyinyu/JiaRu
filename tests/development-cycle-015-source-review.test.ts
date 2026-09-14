import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "finalize-development-cycle-015-source-review.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('review',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['review']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("源图复核只接受固定的保留与排除决策", () => {
  const result = evaluate(["print(json.dumps(sorted(m.DECISIONS)))"]);
  assert.deepEqual(result, [
    "exclude-cropped-or-occluded",
    "exclude-prior-authoritative-source-gate",
    "exclude-quality",
    "exclude-watermark-shortcut",
    "keep-for-complete-mask-annotation",
  ]);
});

test("服从既有权威源图门后仅1张可返修且首批50仍缺49张", () => {
  const result = evaluate(["print(json.dumps({'firstBatchGap':50-1,'formalSupplyGap':424-1}))"]);
  assert.equal(result.firstBatchGap, 49);
  assert.equal(result.formalSupplyGap, 423);
});

test("机器选择摘要使用稳定规范JSON", () => {
  const result = evaluate(["print(json.dumps({'same':m.canonical_sha256(['a','b'])==m.canonical_sha256(['a','b']),'different':m.canonical_sha256(['a','b'])!=m.canonical_sha256(['b','a'])}))"]);
  assert.equal(result.same, true);
  assert.equal(result.different, true);
});
