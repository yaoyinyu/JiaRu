import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "build-development-cycle-013-closure.py");

function run(lines: string[]): Record<string, unknown> {
  const program = [
    "import importlib.util, json, sys",
    `spec = importlib.util.spec_from_file_location('closure', r'${SCRIPT}')`,
    "m = importlib.util.module_from_spec(spec)",
    "sys.modules['closure'] = m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  const output = execFileSync("python", ["-c", program], { encoding: "utf8" });
  return JSON.parse(output.trim()) as Record<string, unknown>;
}

const FIXTURE = [
  "plan = {'cycleId':'nail-texture-development-cycle-013','decision':'pre_registered_high_resolution_roi_pixel_mask_replacement','releaseState':'hold'}",
  "headline = dict(m.EXPECTED_HEADLINE)",
  "ceiling = {'decision':m.EXPECTED_CEILING_DECISION,'headlineEpsilon':.05,'epsilonSweep':[{'epsilon':.05,'summary':{'missing':headline['missingInstances'],'missingImages':headline['missingImages'],'instanceRecall':headline['instanceRecall'],'completeMaskRatio':headline['completeMaskRatio'],'weightedSpuriousNumerator':headline['weightedSpuriousNumerator'],'weightedSpuriousRate':headline['weightedSpuriousRate']}}],'reconstructionFidelity':{'checks':1190,'mismatchCount':0,'ok':True},'margin':{'missingTruthsWithoutAttachableCandidate':16,'weightedSpuriousNumeratorCeiling':27.0,'spuriousAxisReachable':False}}",
  "wilson = {'reconstructionFidelity':{'checks':1190,'mismatchCount':0,'ok':True},'relativeGateResolvability':{'relativeGateInsideBaselineInterval':True,'minDetectableDifferenceAtSameN':.14480412},'requiredSampleSizes':[{'comparison':k,'requiredImagesPerGroup':v} for k,v in m.EXPECTED_REQUIRED_SAMPLE_SIZES.items()]}",
  "roots = {'datasetRoot':False,'trainingRoot':False,'clean98EvaluationRoot':False}",
];

test("循环013关闭合同接受深重放一致且零预算的不可达证据", () => {
  const result = run([...FIXTURE, "facts=m.validate_evidence(plan,ceiling,wilson,roots)", "print(json.dumps(facts))"]);
  assert.equal(result.unattachedMissingTruths, 16);
  assert.equal(result.relativeGateInsideBaselineWilson95, true);
});

test("循环013关闭合同拒绝把可达结论或已有训练目录写成零预算关闭", () => {
  const result = run([
    ...FIXTURE,
    "bad_decision=False",
    "bad_root=False",
    "try:",
    "    ceiling['decision']='reachable'",
    "    m.validate_evidence(plan,ceiling,wilson,roots)",
    "except ValueError: bad_decision=True",
    "ceiling['decision']=m.EXPECTED_CEILING_DECISION",
    "roots['trainingRoot']=True",
    "try:",
    "    m.validate_evidence(plan,ceiling,wilson,roots)",
    "except ValueError: bad_root=True",
    "print(json.dumps({'badDecisionRejected':bad_decision,'existingRootRejected':bad_root}))",
  ]);
  assert.equal(result.badDecisionRejected, true);
  assert.equal(result.existingRootRejected, true);
});

test("循环013关闭合同拒绝Wilson样本量漂移", () => {
  const result = run([
    ...FIXTURE,
    "wilson['requiredSampleSizes'][0]['requiredImagesPerGroup']=931",
    "rejected=False",
    "try:",
    "    m.validate_evidence(plan,ceiling,wilson,roots)",
    "except ValueError: rejected=True",
    "print(json.dumps({'rejected':rejected}))",
  ]);
  assert.equal(result.rejected, true);
});
