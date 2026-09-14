import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "audit-development-cycle-015-repair-stoploss.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('stoploss',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['stoploss']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("止损只接受零新增推理的原分辨率排除决策", () => {
  const result = evaluate(["print(json.dumps({'decision':m.STOPLOSS_DECISION,'file':m.FILE_NAME}))"]);
  assert.equal(result.decision, "exclude-repeated-repair-and-occluded-required-nail");
  assert.equal(result.file, "nail_01063_69417639000000001f005854_0.jpg");
});

test("唯一恢复源图关闭后首批50与正式最低供给缺口回到50和424", () => {
  const result = evaluate(["print(json.dumps({'firstBatchGap':50-0,'formalSupplyGap':424-0}))"]);
  assert.equal(result.firstBatchGap, 50);
  assert.equal(result.formalSupplyGap, 424);
});
