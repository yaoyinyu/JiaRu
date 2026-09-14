import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "audit-development-cycle-015-acceleration-route.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('route',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['route']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("Wilson下界把90张批准真值对应的来源门候选下限定为133张", () => {
  const result = evaluate([
    "import math",
    "lo,hi=m.wilson_interval(120,160)",
    "print(json.dumps({'lo':lo,'hi':hi,'needed':math.ceil(90/lo)}))",
  ]);
  assert.ok(Number(result.lo) > 0.677 && Number(result.lo) < 0.678);
  assert.ok(Number(result.hi) > 0.810 && Number(result.hi) < 0.811);
  assert.equal(result.needed, 133);
});

test("旧50张候选里程碑在点估计下也只能产生37.5张批准图", () => {
  const result = evaluate([
    "rate=120/160",
    "print(json.dumps({'expected':50*rate,'gap':90-50*rate,'decision':m.DECISION}))",
  ]);
  assert.equal(result.expected, 37.5);
  assert.equal(result.gap, 52.5);
  assert.equal(result.decision, "replace_50_candidate_intake_with_133_source_qualified_development_cohort");
});
