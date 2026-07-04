import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import { stringifySourceRecords, type SourceRecord } from "../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

function annotationDoc(fileName: string, sourceGroup: string, polygonCount: number, negative = false) {
  return {
    version: "nail-texture-dataset/v1",
    image: {
      id: fileName.replace(/\.[^.]+$/, ""),
      fileName,
      width: 120,
      height: 80,
      sourceGroup,
      negative,
    },
    annotations: Array.from({ length: polygonCount }, (_, index) => ({
      id: `${fileName}-${index + 1}`,
      label: "nail_texture",
      polygon: [
        { x: 20, y: 10 },
        { x: 35, y: 10 },
        { x: 42, y: 40 },
        { x: 34, y: 65 },
        { x: 18, y: 62 },
        { x: 12, y: 35 },
      ],
    })),
  };
}

function sourceRecord(overrides: Partial<SourceRecord>): SourceRecord {
  return {
    imageId: "sample-001",
    fileName: "sample-001.jpg",
    sourceGroup: "seed-batch-001",
    originType: "reference",
    originRef: "owned reference set",
    license: "owner-authorized-training",
    notes: "sample=reference; background=light",
    negative: false,
    annotationPath: "annotations/raw-json/sample-001.json",
    imagePath: "images/raw/sample-001.jpg",
    annotationCount: 4,
    createdAt: "2026-07-01T00:00:00.000Z",
    updatedAt: "2026-07-01T00:10:00.000Z",
    ...overrides,
  };
}

test("verify-training-dataset-readiness reports all pretrain gates for an empty dataset", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-training-readiness-empty-"));
  const outputPath = path.join(datasetRoot, "metadata", "training-dataset-readiness-release.json");

  let caught: unknown;
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/verify-training-dataset-readiness.ts",
        "--dataset-root",
        datasetRoot,
        "--output",
        outputPath,
      ],
      { cwd: path.resolve(".") }
    );
  } catch (error) {
    caught = error;
  }

  assert.ok(caught, "empty dataset should fail the combined readiness gate");
  const report = JSON.parse((caught as { stdout?: string }).stdout ?? "") as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
    artifacts: { phase1Readiness: { ok: boolean } | null };
  };
  assert.equal(report.ok, false);
  assert.deepEqual(report.steps.map((step) => step.name), [
    "audit-sources-csv",
    "audit-training-source-authorization",
    "audit-phase1-readiness",
  ]);
  assert.ok(report.steps.some((step) => !step.ok));
  assert.equal(report.artifacts.phase1Readiness?.ok, false);
  assert.equal(JSON.parse(await readFile(outputPath, "utf8")).ok, false);
});

test("verify-training-dataset-readiness passes a release-authorized phase1-ready dataset", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-training-readiness-pass-"));
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  const imageDir = path.join(datasetRoot, "images", "raw");
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(annotationDir, { recursive: true });
  await mkdir(imageDir, { recursive: true });
  await mkdir(metadataDir, { recursive: true });

  const split = { train: [] as string[], val: [] as string[], test: [] as string[] };
  const sources: SourceRecord[] = [];

  for (let index = 1; index <= 220; index++) {
    const stem = `sample-${String(index).padStart(3, "0")}`;
    const fileName = `${stem}.jpg`;
    const negative = index > 200;
    const sourceGroup = negative ? "negative-authorized" : index <= 100 ? "user-authorized" : "merchant-authorized";
    const polygonCount = negative ? 0 : 4;
    const subset = index <= 160 ? "train" : index <= 200 ? "val" : "test";
    split[subset].push(fileName);

    await writeFile(
      path.join(annotationDir, `${stem}.json`),
      JSON.stringify(annotationDoc(fileName, sourceGroup, polygonCount, negative), null, 2),
      "utf8"
    );
    await writeFile(path.join(imageDir, fileName), "fake image bytes", "utf8");

    const originType = negative ? "negative" : index <= 100 ? "user" : "merchant";
    const license = negative
      ? "owner-authorized-training"
      : originType === "user"
        ? "user-authorized-internal-training"
        : "merchant-authorized-commercial-training";
    const background = subset === "test" ? (index % 2 === 0 ? "dark" : "mixed") : "light";
    sources.push(
      sourceRecord({
        imageId: stem,
        fileName,
        sourceGroup,
        originType,
        originRef: `${sourceGroup} authorization #${index}`,
        license,
        notes: `sample=${negative ? "negative" : originType}; background=${background}`,
        negative,
        annotationPath: `annotations/raw-json/${stem}.json`,
        imagePath: `images/raw/${fileName}`,
        annotationCount: polygonCount,
      })
    );
  }

  await writeFile(path.join(metadataDir, "split.json"), JSON.stringify(split, null, 2), "utf8");
  await writeFile(path.join(metadataDir, "sources.csv"), stringifySourceRecords(sources), "utf8");

  const outputPath = path.join(metadataDir, "combined-readiness.json");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/verify-training-dataset-readiness.ts",
      "--dataset-root",
      datasetRoot,
      "--output",
      outputPath,
    ],
    { cwd: path.resolve(".") }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
    artifacts: {
      sourceAudit: { ok: boolean };
      sourceAuthorization: { ok: boolean; mode: string };
      phase1Readiness: { ok: boolean; totals: { validMasks: number } };
    };
  };
  assert.equal(report.ok, true);
  assert.deepEqual(report.steps.map((step) => step.ok), [true, true, true]);
  assert.equal(report.artifacts.sourceAudit.ok, true);
  assert.equal(report.artifacts.sourceAuthorization.ok, true);
  assert.equal(report.artifacts.sourceAuthorization.mode, "release");
  assert.equal(report.artifacts.phase1Readiness.ok, true);
  assert.equal(report.artifacts.phase1Readiness.totals.validMasks, 800);
  assert.equal(JSON.parse(await readFile(outputPath, "utf8")).ok, true);
});