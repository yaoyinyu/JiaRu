import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/profile-development-instance-errors.py");

function choose(positiveMass: number, totalMass: number, cooccurring: number, images: number) {
  const code = [
    "import importlib.util, json, pathlib",
    `p=pathlib.Path(${JSON.stringify(script)})`,
    "s=importlib.util.spec_from_file_location('profile_dev_errors_test', p)",
    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
    `print(json.dumps(m.choose_next_variable(${positiveMass}, ${totalMass}, ${cooccurring}, ${images})))`,
  ].join(";");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }));
}

test("正图杂散与漏甲高度共现时选择来源隔离真实正样本补强", () => {
  const result = choose(60.5, 64.5, 17, 25);
  assert.equal(result.selectedVariable, "targeted_source_isolated_real_positive_augmentation");
  assert.equal(result.positiveSpuriousMassShare > 0.9, true);
  assert.equal(result.errorImageMissingCooccurrenceShare, 0.68);
});

test("杂散不与正图漏甲共现时选择单一结构抑制", () => {
  const result = choose(20, 64, 2, 20);
  assert.equal(result.selectedVariable, "single_structural_candidate_suppression");
});
