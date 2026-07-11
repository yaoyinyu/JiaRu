import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("model metric assessment rejects mask regressions", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-metrics-"));
  const baseline = path.join(root, "baseline.json");
  const candidate = path.join(root, "candidate.json");
  const output = path.join(root, "report.json");
  await writeFile(baseline, JSON.stringify({ box_map50: 0.8, seg_map50: 0.7, box_map: 0.4, seg_map: 0.3 }));
  await writeFile(candidate, JSON.stringify({ box_map50: 0.79, seg_map50: 0.5, box_map: 0.39, seg_map: 0.2 }));

  const result = spawnSync("python", [
    "model/training/assess-model-metrics.py",
    "--baseline", baseline,
    "--candidate", `int8=${candidate}`,
    "--output", output,
  ], { encoding: "utf8" });
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, false);
  assert.equal(report.candidates[0].qualityGatePassed, false);
  assert.match(report.candidates[0].errors.join(" "), /mask mAP50 drop/);
});
