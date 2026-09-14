import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "audit-development-cycle-014-positive-capacity.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('capacity',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['capacity']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("容量目标固定为352/932/148且现58图缺口分别为294/874/90", () => {
  const result = evaluate([
    "current=58",
    "print(json.dumps({k:v-current for k,v in m.DEVELOPMENT_TARGETS.items()}))",
  ]);
  assert.equal(result.absoluteMissingRateResolution, 294);
  assert.equal(result.relativeMissingRateResolutionPerGroup, 874);
  assert.equal(result.spuriousRateResolution, 90);
});

test("身份重叠同时检查文件名、图片哈希和来源组", () => {
  const result = evaluate([
    "a=({'a'},{'1'},{'g'})",
    "b=({'a'},{'2'},{'h'})",
    "c=({'b'},{'1'},{'g'})",
    "print(json.dumps({'name':m.overlap(a,b),'hashGroup':m.overlap(a,c)}))",
  ]);
  assert.deepEqual(result.name, { fileNames: 1, imageSha256: 0, sourceGroups: 0 });
  assert.deepEqual(result.hashGroup, { fileNames: 0, imageSha256: 1, sourceGroups: 1 });
});

test("352图开发扩容加全新30/100发布证据至少需要424张新正图", () => {
  const result = evaluate([
    "current=58",
    "candidate_upper_bound=10",
    "need=(352-current)+30+100",
    "print(json.dumps({'need':need,'afterCandidates':need-candidate_upper_bound}))",
  ]);
  assert.equal(result.need, 424);
  assert.equal(result.afterCandidates, 414);
});
