import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/profile-development-missing-transitions.py");
function python(body: string) {
  return JSON.parse(execFileSync("python", ["-c", [
    "import importlib.util, json, pathlib",
    `p=pathlib.Path(${JSON.stringify(script)})`,
    "s=importlib.util.spec_from_file_location('missing_transitions_test', p)",
    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
    body,
  ].join("\n")], { encoding: "utf8" }));
}

test("漏检数相同但甲面身份互换时仍记录新漏和恢复", () => {
  const result = python("print(json.dumps(m.transitions([1, 2], [2, 3])))");
  assert.deepEqual(result.newlyMissedTruthIndices, [3]);
  assert.deepEqual(result.recoveredTruthIndices, [1]);
  assert.deepEqual(result.persistentMissingTruthIndices, [2]);
  assert.equal(result.missingCountDelta, 0);
  assert.equal(result.newMissingImage, false);
  assert.equal(result.fullyRecoveredImage, false);
});

test("整图新漏和完全恢复与既有漏图的实例增减分开", () => {
  const results = python("print(json.dumps([m.transitions([], [1]), m.transitions([1], []), m.transitions([1], [1, 2])]))");
  assert.equal(results[0].newMissingImage, true);
  assert.equal(results[1].fullyRecoveredImage, true);
  assert.equal(results[2].newMissingImage, false);
  assert.equal(results[2].missingCountDelta, 1);
});

test("同名评估图的图片、标签、来源、角色、甲数及覆盖漂移全部拒绝", () => {
  const result = python([
    "row=dict(imageSha256='image', labelSha256='label', sourceGroup='group', role='train-positive', maskCount=2)",
    "first={'same-stem': row}",
    "m.require_same_evaluation([first, {'same-stem': dict(row)}])",
    "rejected=[]",
    "for field in row:",
    "    changed=dict(row); changed[field]='drift'",
    "    try: m.require_same_evaluation([first, {'same-stem': changed}])",
    "    except ValueError: rejected.append(field)",
    "try: m.require_same_evaluation([first, {}])",
    "except ValueError: rejected.append('coverage')",
    "print(json.dumps(rejected))",
  ].join("\n"));
  assert.deepEqual(result, ["imageSha256", "labelSha256", "sourceGroup", "role", "maskCount", "coverage"]);
});

test("区分产品后处理删掉完整候选与原始mask定位失败", () => {
  const results = python([
    "from shapely.geometry import box",
    "truth=(box(.1,.1,.2,.2),1.,True)",
    "partial=(box(.1,.1,.12,.2),.9,True)",
    "common=dict(truth=[truth], missing=[1])",
    "print(json.dumps([m.instance_evidence(dict(common, raw=[truth], kept=[]),1),m.instance_evidence(dict(common, raw=[partial], kept=[partial]),1)]))",
  ].join("\n"));
  assert.equal(results[0].mechanism, "product-postprocessing-removal");
  assert.equal(results[1].mechanism, "retained-mask-below-match-iou");
});

test("视觉决定不能遗漏变动图、错绑标签或直接晋升训练", () => {
  const result = python([
    "row=dict(stem='one', image=dict(sha256='image'), labelSha256='label')",
    "review=dict(stem='one', imageSha256='image', labelSha256='label', originalResolutionReviewed=True, disposition='source-exclude', review='cropped nail')",
    "valid=dict(images=[review], trainingUse='prohibited', releaseState='hold')",
    "counts=m.validate_visual_reviews([row],valid)",
    "rejected=0",
    "for altered in [dict(valid,images=[]),dict(valid,trainingUse='approved'),dict(valid,images=[dict(review,labelSha256='drift')])]:",
    "    try: m.validate_visual_reviews([row],altered)",
    "    except ValueError: rejected+=1",
    "print(json.dumps(dict(counts=counts,rejected=rejected)))",
  ].join("\n"));
  assert.deepEqual(result.counts, { "source-exclude": 1 });
  assert.equal(result.rejected, 3);
});

test("历史合同来源说明可兼容，但阈值与杂散权重不能漂移", () => {
  const result = python([
    "a=dict(contract=dict(scoreThreshold=.25,formalFloorSource='pre-registered-plan'))",
    "b=dict(contract=dict(scoreThreshold=.25,formalFloorSource='immutable-code-default-for-legacy-plan',spuriousWeights=dict(duplicates=1,invalidPredictionMasks=1.5,falsePositives=2)))",
    "c=dict(contract=dict(b['contract'],scoreThreshold=.2))",
    "print(json.dumps([m.semantic_contract(a)==m.semantic_contract(b),m.semantic_contract(a)==m.semantic_contract(c)]))",
  ].join("\n"));
  assert.deepEqual(result, [true, false]);
});
