import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "analyze-development-cycle-014-route-viability.py");

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

test("0.70四裁片完整覆盖带20%上下文的典型中心与边缘甲面", () => {
  const result = evaluate([
    "boxes=[(.04,.04,.10,.16),(.45,.05,.55,.20),(.80,.75,.92,.90),(.05,.75,.18,.92)]",
    "covered=[any(m.crop_covers(box,crop) for crop in m.CROPS.values()) for box in boxes]",
    "print(json.dumps({'covered':covered,'gain':round(1/.7,8)}))",
  ]);
  assert.deepEqual(result.covered, [true, true, true, true]);
  assert.equal(result.gain, 1.42857143);
});

test("五次推理的历史P95投影有余量但最坏投影不足以包含编排开销", () => {
  const result = evaluate([
    "p={'ok':True,'profile':'desktop','totals':{'samples':29},'stats':{'p95Ms':133.7,'maxMs':159.5}}",
    "print(json.dumps(m.analyze_runtime(p)))",
  ]);
  assert.equal(result.inferencePassesPerImage, 5);
  assert.equal(result.linearP95ProjectionMs, 668.5);
  assert.equal(result.linearMaxProjectionMs, 797.5);
  assert.equal(result.desktopBudgetProven, false);
});

test("workers8只节省训练分钟，414图审核吞吐决定日历工期", () => {
  const result = evaluate([
    "t={'referenceRun':{'totalSeconds':490.815},'levers':[{'change':'workers: 0 -> 8','projectedCycle012TotalSeconds':387.9,'projectedSpeedupPercent':22.3}]} ",
    "c={'minimumNewPositiveSupply':{'extendCleanDevelopmentTo352PlusReleaseReserve':424,'remainingAfterCandidateOnlyUpperBound':414}}",
    "print(json.dumps(m.analyze_schedule(t,c)))",
  ]);
  assert.equal(result.workers8SavingPer12EpochRunMinutes, 1.72);
  assert.equal(result.criticalPath, "source-isolated acquisition and original-resolution mask review");
  const scenarios = result.reviewThroughputScenarios as Array<Record<string, number>>;
  assert.deepEqual(scenarios.map((row) => row.daysForRemaining414), [41.4, 16.56, 8.28, 4.14]);
});
