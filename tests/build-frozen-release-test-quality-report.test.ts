import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-frozen-release-test-quality-report.py");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

test("builds an explicit deployment rejection with core and stress evidence", () => {
  const root = mkdtempSync(path.join(tmpdir(), "frozen-quality-"));
  const output = path.join(root, "quality.json");
  const write = (name: string, value: unknown) => { const file = path.join(root, name); writeFileSync(file, JSON.stringify(value)); return file; };
  const items = Array.from({ length: 67 }, (_, index) => ({ lane: index < 45 ? "core" : "stress", fileName: `${index}.jpg` }));
  const snapshot = write("snapshot.json", { snapshotId: "snapshot", decision: "frozen_reviewed_candidate_not_release_ready", trainingUse: "prohibited", counts: { images: 67, masks: 384, coreImages: 45, stressImages: 22 }, itemsSha256: createHash("sha256").update(canonical(items)).digest("hex"), items });
  const evaluationRoot = path.join(root, "evaluation");
  const materialization = write("materialization.json", { ok: true, trainingUse: "prohibited", outputDir: evaluationRoot, counts: { images: 67, masks: 384, parentSourceGroups: 18 }, sourceIsolation: { parentSourceGroupOverlap: [], exactImageHashOverlap: [] } });
  const artifact = (name: string, count: number) => write(`${name}-artifacts.json`, { split: "test", counts: { prediction_labels: count } });
  const metric = (name: string, size: number, count: number, box: number, mask: number) => write(`${name}.json`, { split: "test", imgsz: size, dataset_root: evaluationRoot, box_map50: box, seg_map50: mask, box_map: box - 0.3, seg_map: mask - 0.3, evaluation_artifacts: { index: artifact(name, count) } });
  const baseline = write("baseline.json", { box_map50: 0.853, seg_map50: 0.848 });
  const full512 = metric("full512", 512, 67, 0.837, 0.831);
  const full640 = metric("full640", 640, 67, 0.857, 0.855);
  const core = metric("core", 512, 45, 0.849, 0.852);
  const stress = metric("stress", 512, 22, 0.818, 0.792);
  const assessment = write("assessment.json", { ok: false, candidates: ["release67", "core45", "stress22"].map((label) => ({ label, qualityGatePassed: false })) });
  execFileSync("python", [script, "--snapshot-manifest", snapshot, "--materialization-report", materialization, "--baseline-metrics", baseline, "--full-512", full512, "--full-640", full640, "--core-512", core, "--stress-512", stress, "--assessment", assessment, "--output", output]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.qualityGatePassed, false);
  assert.equal(report.decision, "reject_v6_release_at_deployment_resolution");
  assert.match(report.errors.join(" "), /box mAP50/);
  assert.equal(report.evaluations.stress512.predictionLabels, 22);
});
