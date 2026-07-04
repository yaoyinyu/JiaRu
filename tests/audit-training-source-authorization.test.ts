import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import { stringifySourceRecords, type SourceRecord } from "../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

function sourceRecord(overrides: Partial<SourceRecord>): SourceRecord {
  return {
    imageId: "sample-001",
    fileName: "sample-001.jpg",
    sourceGroup: "seed-batch-001",
    originType: "user",
    originRef: "consent form #001",
    license: "user-authorized-internal-training",
    notes: "",
    negative: false,
    annotationPath: "annotations/raw-json/sample-001.json",
    imagePath: "images/raw/sample-001.jpg",
    annotationCount: 4,
    createdAt: "2026-07-01T00:00:00.000Z",
    updatedAt: "2026-07-01T00:10:00.000Z",
    ...overrides,
  };
}

async function writeSourcesCsv(root: string, records: SourceRecord[]) {
  const metadataDir = path.join(root, "metadata");
  await mkdir(metadataDir, { recursive: true });
  const sourcesPath = path.join(metadataDir, "sources.csv");
  await writeFile(sourcesPath, stringifySourceRecords(records), "utf8");
  return sourcesPath;
}

test("training source authorization persists a structured failure when sources.csv is missing", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-auth-missing-"));
  const outputPath = path.join(datasetRoot, "metadata", "auth-report.json");

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-training-source-authorization.ts",
        "--output",
        outputPath,
      ],
      {
        cwd: path.resolve("."),
        env: { ...process.env, DATASET_ROOT: datasetRoot },
      }
    ),
    (error: unknown) => {
      const report = JSON.parse((error as { stdout?: string }).stdout ?? "");
      assert.equal(report.ok, false);
      assert.equal(report.recordCount, 0);
      assert.equal(report.issues[0]?.code, "missing_sources_csv");
      return true;
    }
  );

  const persisted = JSON.parse(await readFile(outputPath, "utf8"));
  assert.equal(persisted.ok, false);
  assert.equal(persisted.issues[0]?.code, "missing_sources_csv");
});
test("training source authorization rejects an empty source inventory", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-auth-empty-"));
  const outputPath = path.join(datasetRoot, "metadata", "auth-report.json");
  await writeSourcesCsv(datasetRoot, []);

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-training-source-authorization.ts",
        "--output",
        outputPath,
      ],
      {
        cwd: path.resolve("."),
        env: { ...process.env, DATASET_ROOT: datasetRoot },
      }
    ),
    (error: unknown) => {
      const report = JSON.parse((error as { stdout?: string }).stdout ?? "");
      assert.equal(report.ok, false);
      assert.equal(report.recordCount, 0);
      assert.equal(report.issues[0]?.code, "empty_sources_csv");
      return true;
    }
  );

  const persisted = JSON.parse(await readFile(outputPath, "utf8"));
  assert.equal(persisted.issues[0]?.code, "empty_sources_csv");
});
test("training source authorization release mode accepts explicit training permissions", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-auth-pass-"));
  const outputPath = path.join(datasetRoot, "metadata", "auth-report.json");
  await writeSourcesCsv(datasetRoot, [
    sourceRecord({
      imageId: "user-001",
      fileName: "user-001.jpg",
      originType: "user",
      originRef: "consent form #001",
      license: "user-authorized-internal-training",
    }),
    sourceRecord({
      imageId: "merchant-001",
      fileName: "merchant-001.jpg",
      originType: "merchant",
      originRef: "merchant contract #a",
      license: "merchant-authorized-commercial-training",
    }),
    sourceRecord({
      imageId: "public-001",
      fileName: "public-001.jpg",
      originType: "reference",
      originRef: "owned reference set",
      license: "licensed-commercial-training",
    }),
  ]);

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/audit-training-source-authorization.ts",
      "--output",
      outputPath,
    ],
    {
      cwd: path.resolve("."),
      env: { ...process.env, DATASET_ROOT: datasetRoot },
    }
  );

  const report = JSON.parse(stdout);
  assert.equal(report.ok, true);
  assert.equal(report.mode, "release");
  assert.equal(report.recordCount, 3);
  assert.deepEqual(report.issues, []);
  assert.equal(JSON.parse(await readFile(outputPath, "utf8")).ok, true);
});

test("training source authorization release mode blocks web and ambiguous sources", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-auth-block-"));
  await writeSourcesCsv(datasetRoot, [
    sourceRecord({
      imageId: "web-001",
      fileName: "web-001.jpg",
      originType: "web",
      originRef: "manual web sourcing",
      license: "internal-test-only",
    }),
    sourceRecord({
      imageId: "user-002",
      fileName: "user-002.jpg",
      originType: "user",
      originRef: "debug upload",
      license: "internal-training",
    }),
    sourceRecord({
      imageId: "merchant-002",
      fileName: "merchant-002.jpg",
      originType: "merchant",
      originRef: "store album",
      license: "internal-training",
    }),
    sourceRecord({
      imageId: "unknown-001",
      fileName: "unknown-001.jpg",
      originType: "other",
      originRef: "",
      license: "",
    }),
  ]);

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-training-source-authorization.ts",
      ],
      {
        cwd: path.resolve("."),
        env: { ...process.env, DATASET_ROOT: datasetRoot },
      }
    ),
    (error: unknown) => {
      const stdout = (error as { stdout?: string }).stdout ?? "";
      const report = JSON.parse(stdout);
      const codes = report.issues.map((issue: { code: string }) => issue.code);
      assert.equal(report.ok, false);
      assert.ok(codes.includes("release_web_source_not_allowed"));
      assert.ok(codes.includes("release_internal_test_license"));
      assert.ok(codes.includes("release_user_without_authorization"));
      assert.ok(codes.includes("release_merchant_without_authorization"));
      assert.ok(codes.includes("missing_origin_ref"));
      assert.ok(codes.includes("missing_license"));
      return true;
    }
  );
});

test("training source authorization internal mode allows internal-test-only but warns incomplete metadata", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-auth-internal-"));
  await writeSourcesCsv(datasetRoot, [
    sourceRecord({
      imageId: "web-001",
      fileName: "web-001.jpg",
      originType: "web",
      originRef: "manual web sourcing",
      license: "internal-test-only",
    }),
    sourceRecord({
      imageId: "missing-001",
      fileName: "missing-001.jpg",
      originType: "other",
      originRef: "",
      license: "",
    }),
  ]);

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/audit-training-source-authorization.ts",
      "--mode",
      "internal",
    ],
    {
      cwd: path.resolve("."),
      env: { ...process.env, DATASET_ROOT: datasetRoot },
    }
  );

  const report = JSON.parse(stdout);
  const codes = report.issues.map((issue: { code: string }) => issue.code);
  assert.equal(report.ok, true);
  assert.equal(report.mode, "internal");
  assert.ok(codes.includes("missing_origin_ref"));
  assert.ok(codes.includes("missing_license"));
  assert.ok(!codes.includes("release_web_source_not_allowed"));
});
