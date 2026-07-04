import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import test from "node:test";
import {
  auditSourceRecords,
  parseSourceRecords,
  stringifySourceRecords,
} from "../src/lib/nail-texture-dataset.ts";

test("source record audit accepts valid metadata and warns on incomplete provenance", () => {
  const valid = auditSourceRecords([
    {
      imageId: "sample-001",
      fileName: "sample-001.jpg",
      sourceGroup: "seed-batch-001",
      originType: "reference",
      originRef: "local album a",
      license: "internal-test",
      notes: "",
      negative: false,
      annotationPath: "annotations/raw-json/sample-001.json",
      imagePath: "images/raw/sample-001.jpg",
      annotationCount: 4,
      createdAt: "2026-07-01T00:00:00.000Z",
      updatedAt: "2026-07-01T00:10:00.000Z",
    },
  ]);
  assert.equal(valid.ok, true);
  assert.deepEqual(valid.issues, []);

  const warned = auditSourceRecords([
    {
      imageId: "neg-001",
      fileName: "neg-001.jpg",
      sourceGroup: "negative-set-a",
      originType: "other",
      originRef: "",
      license: "",
      notes: "",
      negative: true,
      annotationPath: "annotations/raw-json/neg-001.json",
      imagePath: "images/raw/neg-001.jpg",
      annotationCount: 0,
      createdAt: "2026-07-01T00:00:00.000Z",
      updatedAt: "2026-07-01T00:10:00.000Z",
    },
  ]);
  assert.equal(warned.ok, true);
  assert.ok(warned.issues.some((issue) => issue.code === "missing_origin_ref"));
  assert.ok(warned.issues.some((issue) => issue.code === "missing_license"));
  assert.ok(warned.issues.some((issue) => issue.code === "negative_origin_mismatch"));
});

test("source record audit rejects broken metadata", () => {
  const audit = auditSourceRecords([
    {
      imageId: "",
      fileName: "nested/sample-001.jpg",
      sourceGroup: "",
      originType: "bad" as never,
      originRef: "x",
      license: "y",
      notes: "",
      negative: false,
      annotationPath: "bad/sample-001.json",
      imagePath: "raw/sample-001.bmp",
      annotationCount: -1,
      createdAt: "not-a-date",
      updatedAt: "",
    },
  ]);

  assert.equal(audit.ok, false);
  assert.ok(audit.issues.some((issue) => issue.code === "missing_image_id"));
  assert.ok(audit.issues.some((issue) => issue.code === "invalid_file_name"));
  assert.ok(audit.issues.some((issue) => issue.code === "missing_source_group"));
  assert.ok(audit.issues.some((issue) => issue.code === "invalid_origin_type"));
  assert.ok(audit.issues.some((issue) => issue.code === "invalid_annotation_path"));
  assert.ok(audit.issues.some((issue) => issue.code === "invalid_image_path"));
  assert.ok(audit.issues.some((issue) => issue.code === "invalid_annotation_count"));
  assert.ok(audit.issues.some((issue) => issue.code === "invalid_timestamp"));
});

test("audit-sources-csv script writes json report", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-audit-sources-"));
  const metadataDir = path.join(datasetRoot, "metadata");
  const imageDir = path.join(datasetRoot, "images", "raw");
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  await mkdir(metadataDir, { recursive: true });
  await mkdir(imageDir, { recursive: true });
  await mkdir(annotationDir, { recursive: true });
  await writeFile(path.join(imageDir, "sample-001.jpg"), "image-bytes", "utf8");
  await writeFile(
    path.join(annotationDir, "sample-001.json"),
    JSON.stringify({
      version: "nail-texture-dataset/v1",
      image: { id: "sample-001", fileName: "sample-001.jpg", width: 100, height: 50 },
      annotations: [
        { id: "n1", label: "nail_texture", polygon: [{ x: 1, y: 1 }, { x: 10, y: 1 }, { x: 8, y: 10 }] },
        { id: "n2", label: "nail_texture", polygon: [{ x: 11, y: 1 }, { x: 20, y: 1 }, { x: 18, y: 10 }] },
        { id: "n3", label: "nail_texture", polygon: [{ x: 21, y: 1 }, { x: 30, y: 1 }, { x: 28, y: 10 }] },
        { id: "n4", label: "nail_texture", polygon: [{ x: 31, y: 1 }, { x: 40, y: 1 }, { x: 38, y: 10 }] },
      ],
    }),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "sources.csv"),
    stringifySourceRecords([
      {
        imageId: "sample-001",
        fileName: "sample-001.jpg",
        sourceGroup: "seed-a",
        originType: "reference",
        originRef: "local",
        license: "internal-test",
        notes: "",
        negative: false,
        annotationPath: "annotations/raw-json/sample-001.json",
        imagePath: "images/raw/sample-001.jpg",
        annotationCount: 4,
        createdAt: "2026-07-01T00:00:00.000Z",
        updatedAt: "2026-07-01T00:10:00.000Z",
      },
    ]),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-sources-csv.ts",
      ],
      {
        cwd: process.cwd(),
        env: {
          ...process.env,
          DATASET_ROOT: datasetRoot,
        },
        stdio: "ignore",
      }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 0);
  const report = JSON.parse(
    await readFile(path.join(metadataDir, "sources-audit.json"), "utf8")
  ) as {
    ok: boolean;
    recordCount: number;
    issues: Array<{ code: string }>;
  };
  assert.equal(report.ok, true);
  assert.equal(report.recordCount, 1);
  assert.deepEqual(report.issues, []);

  const parsed = parseSourceRecords(
    await readFile(path.join(metadataDir, "sources.csv"), "utf8")
  );
  assert.equal(parsed.length, 1);
});

test("audit-sources-csv script rejects an empty source inventory", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-audit-sources-empty-"));
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(metadataDir, { recursive: true });
  await writeFile(path.join(metadataDir, "sources.csv"), stringifySourceRecords([]), "utf8");

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", "model/training/audit-sources-csv.ts"],
      {
        cwd: process.cwd(),
        env: { ...process.env, DATASET_ROOT: datasetRoot },
        stdio: "ignore",
      }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const report = JSON.parse(
    await readFile(path.join(metadataDir, "sources-audit.json"), "utf8")
  ) as { ok: boolean; recordCount: number; issues: Array<{ code: string }> };
  assert.equal(report.ok, false);
  assert.equal(report.recordCount, 0);
  assert.ok(report.issues.some((issue) => issue.code === "empty_sources_csv"));
});
test("audit-sources-csv script reports missing sources.csv structurally", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-audit-sources-missing-"));
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(metadataDir, { recursive: true });

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-sources-csv.ts",
      ],
      {
        cwd: process.cwd(),
        env: {
          ...process.env,
          DATASET_ROOT: datasetRoot,
        },
        stdio: "ignore",
      }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const report = JSON.parse(
    await readFile(path.join(metadataDir, "sources-audit.json"), "utf8")
  ) as {
    ok: boolean;
    recordCount: number;
    issues: Array<{ code: string }>;
  };
  assert.equal(report.ok, false);
  assert.equal(report.recordCount, 0);
  assert.ok(report.issues.some((issue) => issue.code === "missing_sources_csv"));
});
test("audit-sources-csv script rejects missing files and annotation count drift", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-audit-sources-disk-"));
  const metadataDir = path.join(datasetRoot, "metadata");
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  await mkdir(metadataDir, { recursive: true });
  await mkdir(annotationDir, { recursive: true });
  await writeFile(
    path.join(annotationDir, "sample-001.json"),
    JSON.stringify({
      version: "nail-texture-dataset/v1",
      image: { id: "sample-001", fileName: "sample-001.jpg", width: 100, height: 50 },
      annotations: [
        { id: "n1", label: "nail_texture", polygon: [{ x: 1, y: 1 }, { x: 10, y: 1 }, { x: 8, y: 10 }] },
        { id: "n2", label: "nail_texture", polygon: [{ x: 20, y: 1 }, { x: 30, y: 1 }, { x: 28, y: 10 }] },
      ],
    }),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "sources.csv"),
    stringifySourceRecords([
      {
        imageId: "sample-001",
        fileName: "sample-001.jpg",
        sourceGroup: "seed-a",
        originType: "reference",
        originRef: "local",
        license: "internal-test",
        notes: "",
        negative: false,
        annotationPath: "annotations/raw-json/sample-001.json",
        imagePath: "images/raw/sample-001.jpg",
        annotationCount: 1,
        createdAt: "2026-07-01T00:00:00.000Z",
        updatedAt: "2026-07-01T00:10:00.000Z",
      },
      {
        imageId: "sample-002",
        fileName: "sample-002.jpg",
        sourceGroup: "seed-a",
        originType: "reference",
        originRef: "local",
        license: "internal-test",
        notes: "",
        negative: false,
        annotationPath: "annotations/raw-json/sample-002.json",
        imagePath: "images/raw/sample-002.jpg",
        annotationCount: 0,
        createdAt: "2026-07-01T00:00:00.000Z",
        updatedAt: "2026-07-01T00:10:00.000Z",
      },
    ]),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-sources-csv.ts",
      ],
      {
        cwd: process.cwd(),
        env: {
          ...process.env,
          DATASET_ROOT: datasetRoot,
        },
        stdio: "ignore",
      }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const report = JSON.parse(
    await readFile(path.join(metadataDir, "sources-audit.json"), "utf8")
  ) as {
    ok: boolean;
    issues: Array<{ code: string; fileName?: string; expected?: number; actual?: number }>;
  };
  assert.equal(report.ok, false);
  assert.ok(report.issues.some((issue) => issue.code === "missing_source_image_file" && issue.fileName === "sample-001.jpg"));
  assert.ok(report.issues.some((issue) => issue.code === "missing_source_annotation_file" && issue.fileName === "sample-002.jpg"));
  const mismatch = report.issues.find((issue) => issue.code === "annotation_count_mismatch");
  assert.equal(mismatch?.expected, 1);
  assert.equal(mismatch?.actual, 2);
});
