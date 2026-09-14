import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "audit-development-cycle-015-source-supply.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('supply',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['supply']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("候选只要文件、哈希或来源组任一交叠就必须拒绝", () => {
  const result = evaluate([
    "used={'fileName':{'a.jpg'},'imageSha256':{'1'*64},'sourceGroup':{'g'}}",
    "rows=[{'fileName':'A.JPG','imageSha256':'2'*64,'sourceGroup':'h'},{'fileName':'b.jpg','imageSha256':'1'*64,'sourceGroup':'h'},{'fileName':'c.jpg','imageSha256':'3'*64,'sourceGroup':'g'}]",
    "print(json.dumps([m.overlap_reasons(row,used) for row in rows]))",
  ]);
  assert.deepEqual(result, [["fileName"], ["imageSha256"], ["sourceGroup"]]);
});

test("首批50张在恢复7张后仍至少需要43张新候选", () => {
  const result = evaluate([
    "print(json.dumps({'firstBatchGap':m.TARGET_FIRST_BATCH-7,'totalGap':(m.TARGET_CLEAN_DEVELOPMENT-58)+m.FRESH_CALIBRATION_RESERVE+m.FRESH_POSITIVE_HOLDOUT_RESERVE-7}))",
  ]);
  assert.equal(result.firstBatchGap, 43);
  assert.equal(result.totalGap, 417);
});

test("最早可判别的148图开发门仍需90张批准正图", () => {
  const result = evaluate(["print(json.dumps({'gap':148-58}))"]);
  assert.equal(result.gap, 90);
});
