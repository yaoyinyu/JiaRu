import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "evaluate-development-cycle-014-multicrop-pilot.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('pilot',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['pilot']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("固定0.70四裁片映射到像素边界", () => {
  const result = evaluate([
    "c={'fixedFallbackCrops':{'topLeft':[0,0,.7,.7],'topRight':[.3,0,1,.7],'bottomLeft':[0,.3,.7,1],'bottomRight':[.3,.3,1,1]}}",
    "items=[m.pixel_crop(crop,1000,800) for _,crop in m.normalized_crops(c)]",
    "print(json.dumps(items))",
  ]);
  assert.deepEqual(result, [[0, 0, 700, 560], [300, 0, 1000, 560], [0, 240, 700, 800], [300, 240, 1000, 800]]);
});

test("内部裁边mask拒绝而图像外边界mask允许", () => {
  const result = evaluate([
    "import numpy as np",
    "internal=m.touches_internal_edge(np.array([[2,20],[20,20],[20,40]]),(300,0,1000,560),(1000,800),3)",
    "outer=m.touches_internal_edge(np.array([[2,20],[20,20],[20,40]]),(0,0,700,560),(1000,800),3)",
    "print(json.dumps({'internal':internal,'outer':outer}))",
  ]);
  assert.equal(result.internal, true);
  assert.equal(result.outer, false);
});

test("质量结论必须按allRequired且禁止用单轴改善晋升", () => {
  const result = evaluate([
    "b={'summary':{'instanceRecall':.94,'completeMaskRatio':.84,'missingImageRate':.22,'weightedSpuriousRate':.09,'directlyExtractableRate':.5,'matched':333,'completeMasks':297,'missing':21,'missingImages':13,'duplicates':5,'falsePositives':10,'invalidPredictionMasks':6}}",
    "p={'summary':{'evaluationImages':98,'instanceRecall':.96,'completeMaskRatio':.86,'missingImageRate':.08,'weightedSpuriousRate':.03,'directlyExtractableRate':.6,'matched':340,'completeMasks':305,'missing':14,'missingImages':4,'duplicates':4,'falsePositives':4,'invalidPredictionMasks':5}}",
    "f={'minimumInstanceRecall':.9,'minimumCompleteMaskRatio':.85,'maximumMissingImageRate':.1,'maximumWeightedSpuriousRate':.02}",
    "print(json.dumps(m.compare(b,p,f)))",
  ]);
  assert.equal(result.allRequired, false);
  assert.equal(result.qualityImprovementWithoutCoreRegression, true);
});
