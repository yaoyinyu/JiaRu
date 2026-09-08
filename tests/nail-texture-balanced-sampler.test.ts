import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/nail_texture_balanced_sampler.py");

function sha256OfFile(filePath: string): string {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function runSampler(args: string[]): Record<string, unknown> {
  return JSON.parse(runSamplerRaw(args)) as Record<string, unknown>;
}

function runSamplerRaw(args: string[]): string {
  return execFileSync("python", [script, ...args], {
    encoding: "utf-8",
    cwd: path.resolve("."),
  });
}

function makeFixtureRoot(): string {
  return mkdtempSync(path.join(tmpdir(), "balanced-sampler-"));
}

test("build-group-map filters the train split and binds the report identity", () => {
  const root = makeFixtureRoot();
  const reportPath = path.join(root, "materialization.json");
  const report = {
    schemaVersion: 1,
    records: [
      { fileName: "b.jpg", role: "train-positive", sourceGroup: "group-b", developmentSplit: "train", maskCount: 2 },
      { fileName: "a.jpg", role: "train-positive", sourceGroup: "group-a", developmentSplit: "train", maskCount: 1 },
      { fileName: "v.jpg", role: "train-positive", sourceGroup: "group-a", developmentSplit: "val", maskCount: 1 },
    ],
  };
  writeFileSync(reportPath, JSON.stringify(report));
  const outputPath = path.join(root, "group-map.json");
  const result = JSON.parse(runSamplerRaw(["build-group-map", "--materialization-report", reportPath, "--output", outputPath]));
  assert.equal(result.ok, true);
  assert.equal(result.counts.trainImages, 2);
  assert.equal(result.counts.sourceGroups, 2);
  assert.equal(result.sha256, sha256OfFile(outputPath));
  const map = JSON.parse(readFileSync(outputPath, "utf-8"));
  assert.deepEqual(map.images.map((row: { stem: string }) => row.stem), ["a", "b"]);
  assert.equal(map.source.materializationReportSha256, sha256OfFile(reportPath));
});

test("build-group-map rejects duplicate train stems", () => {
  const root = makeFixtureRoot();
  const reportPath = path.join(root, "materialization.json");
  const report = {
    schemaVersion: 1,
    records: [
      { fileName: "a.jpg", role: "train-positive", sourceGroup: "group-a", developmentSplit: "train", maskCount: 1 },
      { fileName: "a.png", role: "train-positive", sourceGroup: "group-b", developmentSplit: "train", maskCount: 1 },
    ],
  };
  writeFileSync(reportPath, JSON.stringify(report));
  const result = spawnSync("python", [
    script,
    "build-group-map",
    "--materialization-report",
    reportPath,
    "--output",
    path.join(root, "group-map.json"),
  ]);
  assert.notEqual(result.status, 0);
});

test("self-check proves equal quotas, coverage, determinism and epoch variation", () => {
  const root = makeFixtureRoot();
  const mapPath = path.join(root, "group-map.json");
  const sizes: Record<string, number> = { g1: 1, g2: 2, g3: 3, g4: 4, g5: 5, g6: 6, g7: 9 };
  const images: Array<{ fileName: string; stem: string; sourceGroup: string; role: string }> = [];
  let counter = 0;
  for (const [group, size] of Object.entries(sizes)) {
    for (let index = 0; index < size; index += 1) {
      counter += 1;
      const stem = `s${String(counter).padStart(3, "0")}`;
      images.push({ fileName: `${stem}.jpg`, stem, sourceGroup: group, role: "train-positive" });
    }
  }
  writeFileSync(
    mapPath,
    JSON.stringify({ schemaVersion: 1, mode: "test", seed: 20260908, source: {}, counts: {}, images })
  );
  const check = runSampler(["self-check", "--group-map", mapPath, "--epochs", "6"]) as {
    ok: boolean;
    trainImages: number;
    sourceGroups: number;
    quotaMin: number;
    quotaMax: number;
    coverageComplete: boolean;
    deterministic: boolean;
    epochOrderVaries: boolean;
  };
  assert.equal(check.ok, true);
  assert.equal(check.trainImages, 30);
  assert.equal(check.sourceGroups, 7);
  assert.equal(check.quotaMin, 4);
  assert.equal(check.quotaMax, 5);
  assert.equal(check.coverageComplete, true);
  assert.equal(check.deterministic, true);
  assert.equal(check.epochOrderVaries, true);
});

test("patched dataloader balances the train epoch and keeps the validation order intact", () => {
  const root = makeFixtureRoot();
  const mapPath = path.join(root, "group-map.json");
  const sizes: Record<string, number> = { g1: 1, g2: 2, g3: 3, g4: 4, g5: 5, g6: 6, g7: 9 };
  const images: Array<{ fileName: string; stem: string; sourceGroup: string; role: string }> = [];
  let counter = 0;
  for (const [group, size] of Object.entries(sizes)) {
    for (let index = 0; index < size; index += 1) {
      counter += 1;
      const stem = `s${String(counter).padStart(3, "0")}`;
      images.push({ fileName: `${stem}.jpg`, stem, sourceGroup: group, role: "train-positive" });
    }
  }
  writeFileSync(
    mapPath,
    JSON.stringify({ schemaVersion: 1, mode: "test", seed: 20260908, source: {}, counts: {}, images })
  );
  const check = runSampler(["loader-self-check", "--group-map", mapPath]) as {
    ok: boolean;
    trainSamplesPerEpoch: number;
    expectedBatchesPerEpoch: number;
    trainLoaderLength: number;
    trainGroupCountsMatchQuotas: boolean;
    secondEpochDiffers: boolean;
    validationOrderSequential: boolean;
  };
  assert.equal(check.ok, true);
  assert.equal(check.trainSamplesPerEpoch, 30);
  assert.equal(check.expectedBatchesPerEpoch, 8);
  assert.equal(check.trainLoaderLength, 8);
  assert.equal(check.trainGroupCountsMatchQuotas, true);
  assert.equal(check.secondEpochDiffers, true);
  assert.equal(check.validationOrderSequential, true);
});
