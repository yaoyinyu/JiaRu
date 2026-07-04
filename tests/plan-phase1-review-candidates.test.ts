import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { stringifySourceRecords, type SourceRecord } from "../src/lib/nail-texture-dataset.ts";

function annotationDoc(fileName: string, polygonCount: number, negative = false) {
  return {
    version: "nail-texture-dataset/v1",
    image: {
      id: fileName.replace(/\.[^.]+$/, ""),
      fileName,
      width: 100,
      height: 50,
      sourceGroup: "review-test",
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

function sourceRecord(
  fileName: string,
  annotationCount: number,
  notes = "sample=ai_generated; background=light",
  negative = false
): SourceRecord {
  const stem = fileName.replace(/\.[^.]+$/, "");
  return {
    imageId: stem,
    fileName,
    sourceGroup: "review-test",
    originType: negative ? "negative" : "other",
    originRef: "local-test",
    license: "internal-test",
    notes,
    negative,
    annotationPath: `annotations/raw-json/${stem}.json`,
    imagePath: `images/raw/${fileName}`,
    annotationCount,
    createdAt: "2026-07-05T00:00:00.000Z",
    updatedAt: "2026-07-05T00:00:00.000Z",
  };
}

async function createDatasetRoot() {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "phase1-review-candidates-"));
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(annotationDir, { recursive: true });
  await mkdir(metadataDir, { recursive: true });
  return { datasetRoot, annotationDir, metadataDir };
}

function runPlanner(datasetRoot: string, args: string[] = []) {
  return new Promise<{ code: number; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/plan-phase1-review-candidates.ts",
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

test("plan-phase1-review-candidates ranks complex and possible negative samples", async () => {
  const { datasetRoot, annotationDir, metadataDir } = await createDatasetRoot();
  const records = [
    sourceRecord("dark-galaxy-chrome.jpg", 4, "sample=ai_generated; background=dark"),
    sourceRecord("plain-low-detection.jpg", 1, "sample=ai_generated; background=plain"),
    sourceRecord("regular-pink.jpg", 5),
  ];
  for (const record of records) {
    await writeFile(
      path.join(annotationDir, record.annotationPath.replace("annotations/raw-json/", "")),
      JSON.stringify(annotationDoc(record.fileName, record.annotationCount), null, 2),
      "utf8"
    );
  }
  await writeFile(path.join(metadataDir, "sources.csv"), stringifySourceRecords(records), "utf8");
  await writeFile(
    path.join(metadataDir, "split.json"),
    JSON.stringify(
      {
        train: ["plain-low-detection.jpg"],
        val: ["regular-pink.jpg"],
        test: ["dark-galaxy-chrome.jpg"],
      },
      null,
      2
    ),
    "utf8"
  );

  const result = await runPlanner(datasetRoot, ["--top", "5"]);

  assert.equal(result.code, 0, result.stderr);
  const report = JSON.parse(result.stdout) as {
    complexBackgroundCandidates: Array<{ fileName: string; suggestedCommand: string }>;
    possibleNegativeCandidates: Array<{ fileName: string; risk: string; suggestedCommand: string }>;
    warnings: string[];
  };
  assert.equal(report.complexBackgroundCandidates[0].fileName, "dark-galaxy-chrome.jpg");
  assert.match(report.complexBackgroundCandidates[0].suggestedCommand, /complex_background/);
  assert.equal(report.possibleNegativeCandidates[0].fileName, "plain-low-detection.jpg");
  assert.equal(report.possibleNegativeCandidates[0].risk, "high");
  assert.match(report.possibleNegativeCandidates[0].suggestedCommand, /visual review confirms/);
  assert.ok(report.warnings.some((warning) => warning.includes("negative sample")));

  const persisted = JSON.parse(
    await readFile(path.join(metadataDir, "phase1-review-candidates.json"), "utf8")
  ) as { counts: { sources: number } };
  assert.equal(persisted.counts.sources, 3);
  const csv = await readFile(path.join(metadataDir, "phase1-review-candidates.csv"), "utf8");
  assert.match(csv, /dark-galaxy-chrome\.jpg/);
  assert.match(csv, /plain-low-detection\.jpg/);
});

test("plan-phase1-review-candidates emits safe command for empty reviewed negative candidates", async () => {
  const { datasetRoot, annotationDir, metadataDir } = await createDatasetRoot();
  const records = [
    sourceRecord(
      "empty-background.jpg",
      0,
      "sample=background; background=plain; reason=manual_review"
    ),
  ];
  await writeFile(
    path.join(annotationDir, "empty-background.json"),
    JSON.stringify(annotationDoc("empty-background.jpg", 0), null, 2),
    "utf8"
  );
  await writeFile(path.join(metadataDir, "sources.csv"), stringifySourceRecords(records), "utf8");
  await writeFile(
    path.join(metadataDir, "split.json"),
    JSON.stringify({ train: [], val: [], test: ["empty-background.jpg"] }, null, 2),
    "utf8"
  );

  const result = await runPlanner(datasetRoot);

  assert.equal(result.code, 0, result.stderr);
  const report = JSON.parse(result.stdout) as {
    possibleNegativeCandidates: Array<{ fileName: string; risk: string; suggestedCommand: string }>;
  };
  assert.equal(report.possibleNegativeCandidates[0].fileName, "empty-background.jpg");
  assert.equal(report.possibleNegativeCandidates[0].risk, "medium");
  assert.match(report.possibleNegativeCandidates[0].suggestedCommand, /--negative true/);
  assert.match(report.possibleNegativeCandidates[0].suggestedCommand, /--clear-annotations/);
});
