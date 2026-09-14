import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";

const SCRIPT = path.join(process.cwd(), "model", "training", "build-pca-multipoint-sam-prompts.py");

function evaluate(lines: string[]): Record<string, unknown> {
  const code = [
    "import importlib.util, json, sys",
    `spec=importlib.util.spec_from_file_location('pca_prompts',r'${SCRIPT}')`,
    "m=importlib.util.module_from_spec(spec)",
    "sys.modules['pca_prompts']=m",
    "spec.loader.exec_module(m)",
    ...lines,
  ].join("\n");
  return JSON.parse(execFileSync("python", ["-c", code], { encoding: "utf8" }).trim()) as Record<string, unknown>;
}

test("PCA多点提示在polygon内部并带扩展框与四角负点", () => {
  const result = evaluate([
    "polygon=[{'x':40,'y':20},{'x':60,'y':20},{'x':60,'y':80},{'x':40,'y':80}]",
    "box,pos,neg=m.build_prompt_for_polygon(polygon,100,100,0.15)",
    "print(json.dumps({'box':box,'positive':pos,'negative':neg}))",
  ]);
  const box = result.box as number[];
  const positive = result.positive as number[][];
  const negative = result.negative as number[][];
  assert.equal(positive.length, 3);
  assert.equal(negative.length, 4);
  assert.ok(box[0] < 0.4 && box[1] < 0.2 && box[2] > 0.6 && box[3] > 0.8);
  for (const [x, y] of positive) {
    assert.ok(x >= 0.4 && x <= 0.6);
    assert.ok(y >= 0.2 && y <= 0.8);
  }
});

test("过小polygon被拒绝而不生成伪提示", () => {
  const result = evaluate([
    "try:",
    " m.build_prompt_for_polygon([{'x':1,'y':1},{'x':2,'y':1},{'x':2,'y':2}],100,100,0.15); out={'rejected':False}",
    "except ValueError as e:",
    " out={'rejected':True,'message':str(e)}",
    "print(json.dumps(out,ensure_ascii=False))",
  ]);
  assert.equal(result.rejected, true);
});
