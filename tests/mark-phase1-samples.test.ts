import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  parseSourceRecords,
  stringifySourceRecords,
  type SourceRecord,
} from "../src/lib/nail-texture-dataset.ts";

function annotationDoc(fileName: string, polygonCount: number, negative = false) {
  return {
    version: "nail-texture-dataset/v1",
    image: {
      id: fileName.replace(/\.[^.]+$/, ""),
      fileName,
      width: 100,
      height: 50,
      sourceGroup: "test-batch",
      negative,
    },
    annotations: Array.from({ length: polygonCount }, (_, index) => ({
      id: `${fileName}-${index + 1}`,
      label: "nail_texture",
      polygon: [
        { x: 10, y: 10 },
        { x: 20, y: 10 },
        { x: 22, y: 25 },
        { x: 18, y: 40 },
        { x: 8, y: 38 },
        { x: 6, y: 24 },
      ],
    })),
  };
}

function sourceRecord(fileName: string, annotationCount: number): SourceRecord {
  const stem = fileName.replace(/\.[^.]+$/, "");
  return {
    imageId: stem,
    fileName,
    sourceGroup: "test-batch",
    originType: "other",
    originRef: "local-test",
    license: "internal-test",
    notes: "sample=ai_generated; background=light",
    negative: false,
    annotationPath: `annotations/raw-json/${stem}.json`,
    imagePath: `images/raw/${fileName}`,
    annotationCount,
    createdAt: "2026-07-04T00:00:00.000Z",
    updatedAt: "2026-07-04T00:00:00.000Z",
  };
}

async function createDatasetRoot() {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "mark-phase1-samples-"));
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(annotationDir, { recursive: true });
  await mkdir(metadataDir, { recursive: true });
  return { datasetRoot, annotationDir, metadataDir };
}

function runMarker(args: string[], datasetRoot: string) {
  return new Promise<{ code: number; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/mark-phase1-samples.ts",
        "--dataset-root",
        datasetRoot,
        ...args,
      ],
      {
        cwd: path.resolve("."),
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += String(chunk)));
    child.stderr.on("data", (chunk) => (stderr += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => resolve({ code: code ?? 0, stdout, stderr }));
  });
}

test("mark-phase1-samples marks complex background samples and moves them into test split", async () => {
  const { datasetRoot, annotationDir, metadataDir } = await createDatasetRoot();
  await writeFile(
    path.join(annotationDir, "complex-a.json"),
    JSON.stringify(annotationDoc("complex-a.jpg", 4), null, 2),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "sources.csv"),
    stringifySourceRecords([sourceRecord("complex-a.jpg", 4)]),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "split.json"),
    JSON.stringify({ train: ["complex-a.jpg"], val: [], test: [] }, null, 2),
    "utf8"
  );

  const result = await runMarker(
    [
      "--file",
      "complex-a.jpg",
      "--background",
      "mixed",
      "--reason",
      "complex_background",
      "--sample",
      "ai_generated",
      "--ensure-test",
    ],
    datasetRoot
  );

  assert.equal(result.code, 0, result.stderr);
  const split = JSON.parse(await readFile(path.join(metadataDir, "split.json"), "utf8")) as {
    train: string[];
    test: string[];
  };
  assert.deepEqual(split.train, []);
  assert.deepEqual(split.test, ["complex-a.jpg"]);

  const records = parseSourceRecords(await readFile(path.join(metadataDir, "sources.csv"), "utf8"));
  assert.match(records[0].notes, /background=mixed/);
  assert.match(records[0].notes, /reason=complex_background/);

  const report = JSON.parse(
    await readFile(path.join(metadataDir, "phase1-sample-marking-report.json"), "utf8")
  ) as { changes: Array<{ movedToTest: boolean }> };
  assert.equal(report.changes[0].movedToTest, true);
});

test("mark-phase1-samples rejects negative samples that still have annotations unless explicitly cleared", async () => {
  const { datasetRoot, annotationDir, metadataDir } = await createDatasetRoot();
  await writeFile(
    path.join(annotationDir, "not-negative.json"),
    JSON.stringify(annotationDoc("not-negative.jpg", 2), null, 2),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "sources.csv"),
    stringifySourceRecords([sourceRecord("not-negative.jpg", 2)]),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "split.json"),
    JSON.stringify({ train: [], val: [], test: ["not-negative.jpg"] }, null, 2),
    "utf8"
  );

  const result = await runMarker(
    ["--file", "not-negative.jpg", "--negative", "true", "--ensure-test"],
    datasetRoot
  );

  assert.equal(result.code, 1);
  assert.match(result.stderr, /still has 2 annotations/);
});

test("mark-phase1-samples can clear reviewed negative samples and sync sources", async () => {
  const { datasetRoot, annotationDir, metadataDir } = await createDatasetRoot();
  await writeFile(
    path.join(annotationDir, "negative-a.json"),
    JSON.stringify(annotationDoc("negative-a.jpg", 0), null, 2),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "sources.csv"),
    stringifySourceRecords([sourceRecord("negative-a.jpg", 0)]),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "split.json"),
    JSON.stringify({ train: [], val: ["negative-a.jpg"], test: [] }, null, 2),
    "utf8"
  );

  const result = await runMarker(
    [
      "--file",
      "negative-a.jpg",
      "--negative",
      "true",
      "--clear-annotations",
      "--ensure-test",
    ],
    datasetRoot
  );

  assert.equal(result.code, 0, result.stderr);
  const doc = JSON.parse(await readFile(path.join(annotationDir, "negative-a.json"), "utf8")) as {
    image: { negative: boolean };
    annotations: unknown[];
  };
  assert.equal(doc.image.negative, true);
  assert.deepEqual(doc.annotations, []);

  const records = parseSourceRecords(await readFile(path.join(metadataDir, "sources.csv"), "utf8"));
  assert.equal(records[0].negative, true);
  assert.equal(records[0].originType, "negative");
  assert.match(records[0].notes, /reason=negative_sample/);

  const split = JSON.parse(await readFile(path.join(metadataDir, "split.json"), "utf8")) as {
    val: string[];
    test: string[];
  };
  assert.deepEqual(split.val, []);
  assert.deepEqual(split.test, ["negative-a.jpg"]);
});
