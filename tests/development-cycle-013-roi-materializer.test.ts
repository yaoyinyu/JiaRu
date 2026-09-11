import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

function run(code: string): unknown {
  const output = execFileSync("python", ["-c", code], { encoding: "utf8" });
  return JSON.parse(output);
}

const load = [
  "import importlib.util,json,pathlib,numpy as np",
  "p=pathlib.Path('model/training/materialize-development-cycle-013-roi-dataset.py')",
  "s=importlib.util.spec_from_file_location('cycle013_materializer',p)",
  "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
].join("; ");

test("cycle013 internal validation split is deterministic and source-group atomic", () => {
  const result = run([
    load,
    "groups={f'g{i}' for i in range(30)}",
    "a=m.select_validation_groups(groups,6,20260910)",
    "b=m.select_validation_groups(groups,6,20260910)",
    "print(json.dumps({'same':a==b,'count':len(a),'overlap':len(a & (groups-a)),'groups':sorted(a)}))",
  ].join("; ")) as { same: boolean; count: number; overlap: number; groups: string[] };
  assert.equal(result.same, true);
  assert.equal(result.count, 6);
  assert.equal(result.overlap, 0);
  assert.equal(new Set(result.groups).size, 6);
});

test("cycle013 proposal association keeps one best proposal per truth and rejects ambiguity", () => {
  const result = run([
    load,
    "truths=[[(0.1,0.1),(0.3,0.1),(0.3,0.4),(0.1,0.4)],[(0.65,0.1),(0.85,0.1),(0.85,0.4),(0.65,0.4)]]",
    "boxes=np.asarray([[9,9,31,41],[12,12,29,39],[64,9,86,41],[20,5,75,45]],dtype=np.float32)",
    "scores=np.asarray([0.7,0.9,0.8,0.95],dtype=np.float32)",
    "polys=[np.asarray([[9,9],[31,9],[31,41],[9,41]]),np.asarray([[12,12],[29,12],[29,39],[12,39]]),np.asarray([[64,9],[86,9],[86,41],[64,41]]),np.asarray([[20,5],[75,5],[75,45],[20,45]])]",
    "selected,counts=m.associate_proposals(boxes,scores,polys,truths,100,100)",
    "print(json.dumps({'truths':sorted(selected),'p0':selected[0]['proposalIndex'],'p1':selected[1]['proposalIndex'],'counts':counts}))",
  ].join("; ")) as { truths: number[]; p0: number; p1: number; counts: Record<string, number> };
  assert.deepEqual(result.truths, [0, 1]);
  assert.equal(result.p0, 0);
  assert.equal(result.p1, 2);
  assert.equal(result.counts.ambiguousProposals, 1);
  assert.equal(result.counts.duplicateTruthProposalsSuppressed, 1);
});

test("cycle013 crop mapping rejects clipped truth and preserves an interior polygon", () => {
  const result = run([
    load,
    "truth=[(0.2,0.2),(0.4,0.2),(0.4,0.5),(0.2,0.5)]",
    "inside=m.transformed_truth(truth,100,100,(10,10,60,60))",
    "clipped=m.transformed_truth(truth,100,100,(20,20,40,50))",
    "print(json.dumps({'inside':inside,'clipped':clipped}))",
  ].join("; ")) as { inside: number[][]; clipped: null };
  assert.equal(result.clipped, null);
  assert.ok(result.inside.every(([x, y]) => x > 0 && x < 1 && y > 0 && y < 1));
});
