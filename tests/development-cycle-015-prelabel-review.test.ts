import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "finalize-development-cycle-015-prelabel-review.py");

function classify(expected: number, candidates: number): string {
  const code = [
    "import importlib.util,sys",
    `spec=importlib.util.spec_from_file_location('review',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec);sys.modules['review']=m;spec.loader.exec_module(m)",
    `print(m.required_disposition(${expected},${candidates}))`,
  ].join("\n");
  return execFileSync("python", ["-c", code], { encoding: "utf8" }).trim();
}

test("候选少于完整甲面时进入漏甲返修", () => {
  assert.equal(classify(10, 8), "rework_missing_nails");
});

test("候选多于完整甲面时进入重复或杂散返修", () => {
  assert.equal(classify(10, 11), "rework_duplicate_or_spurious_candidates");
});

test("计数相等只进入逐甲边界复核而不自动批准", () => {
  assert.equal(classify(5, 5), "advance_to_per_nail_boundary_review");
});
