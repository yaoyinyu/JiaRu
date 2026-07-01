import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

function annotationDoc(
  fileName: string,
  sourceGroup: string,
  polygonCount: number,
  negative = false
) {
  return {
    version: "nail-texture-dataset/v1",
    image: {
      id: fileName.replace(/\.[^.]+$/, ""),
      fileName,
      width: 100,
      height: 50,
      sourceGroup,
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
        { x: 9, y: 14 },
      ],
    })),
  };
}

test("plan-phase1-collection turns readiness gaps into actionable priorities", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-phase1-plan-small-"));
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(annotationDir, { recursive: true });
  await mkdir(metadataDir, { recursive: true });

  await writeFile(
    path.join(annotationDir, "sample-a.json"),
    JSON.stringify(annotationDoc("sample-a.jpg", "seed-a", 4), null, 2),
    "utf8"
  );
  await writeFile(
    path.join(annotationDir, "sample-b.json"),
    JSON.stringify(annotationDoc("sample-b.jpg", "seed-b", 3), null, 2),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "split.json"),
    JSON.stringify({ train: ["sample-a.jpg"], val: [], test: ["sample-b.jpg"] }, null, 2),
    "utf8"
  );
  await writeFile(
    path.join(metadataDir, "sources.csv"),
    [
      "imageId,fileName,sourceGroup,originType,originRef,license,notes,negative,annotationPath,imagePath,annotationCount,createdAt,updatedAt",
      "sample-a,sample-a.jpg,seed-a,reference,local,internal-test,\"sample=reference; background=light\",false,annotations/raw-json/sample-a.json,images/raw/sample-a.jpg,4,2026-07-01T00:00:00.000Z,2026-07-01T00:00:00.000Z",
      "sample-b,sample-b.jpg,seed-b,reference,local,internal-test,\"sample=reference; background=dark\",false,annotations/raw-json/sample-b.json,images/raw/sample-b.jpg,3,2026-07-01T00:00:00.000Z,2026-07-01T00:00:00.000Z",
      "",
    ].join("\n"),
    "utf8"
  );

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", "model/training/plan-phase1-collection.ts"],
      {
        cwd: path.resolve("."),
        env: { ...process.env, DATASET_ROOT: datasetRoot },
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 1) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    remaining: { images: number; validMasks: number };
    derived: { nextBatchTargetImages: number; estimatedBatchesRemaining: number };
    priorities: Array<{ id: string }>;
    suggestedCommands: string[];
  };
  assert.equal(report.remaining.images, 198);
  assert.equal(report.remaining.validMasks, 793);
  assert.equal(report.derived.nextBatchTargetImages, 50);
  assert.ok(report.derived.estimatedBatchesRemaining >= 4);
  assert.ok(report.priorities.some((item) => item.id === "add-negative-test-sample"));
  assert.ok(report.priorities.some((item) => item.id === "expand-positive-dataset"));
  const expandPriority = report.priorities.find((item) => item.id === "expand-positive-dataset") as
    | { id: string; title?: string }
    | undefined;
  assert.equal(expandPriority?.title, "继续扩充 Phase 1 正样本种子集");
  assert.ok(report.suggestedCommands.some((command) => command.includes("run-reviewed-batch-import-pipeline.ts")));
});

test("plan-phase1-collection reports done when readiness gate already passes", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-phase1-plan-ok-"));
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  const metadataDir = path.join(datasetRoot, "metadata");
  await mkdir(annotationDir, { recursive: true });
  await mkdir(metadataDir, { recursive: true });

  const split = { train: [] as string[], val: [] as string[], test: [] as string[] };
  const sourceRows = [
    "imageId,fileName,sourceGroup,originType,originRef,license,notes,negative,annotationPath,imagePath,annotationCount,createdAt,updatedAt",
  ];
  for (let index = 1; index <= 220; index++) {
    const fileName = `sample-${index}.jpg`;
    const negative = index > 200;
    const sourceGroup = negative ? "negative-c" : index <= 80 ? "reference-a" : "merchant-b";
    const polygonCount = negative ? 0 : 4;
    await writeFile(
      path.join(annotationDir, `sample-${index}.json`),
      JSON.stringify(annotationDoc(fileName, sourceGroup, polygonCount, negative), null, 2),
      "utf8"
    );
    const subset = index <= 160 ? "train" : index <= 200 ? "val" : "test";
    split[subset].push(fileName);
    const sampleKind = negative ? "negative" : index <= 140 ? "merchant" : "reference";
    const background =
      subset === "test" ? (index % 2 === 0 ? "dark" : "mixed") : index % 2 === 0 ? "light" : "dark";
    const originType = negative ? "negative" : "reference";
    sourceRows.push(
      [
        `sample-${index}`,
        fileName,
        sourceGroup,
        originType,
        "local",
        "internal-test",
        `"sample=${sampleKind}; background=${background}"`,
        String(negative),
        `annotations/raw-json/sample-${index}.json`,
        `images/raw/${fileName}`,
        String(polygonCount),
        "2026-07-01T00:00:00.000Z",
        "2026-07-01T00:00:00.000Z",
      ].join(",")
    );
  }
  sourceRows.push("");

  await writeFile(path.join(metadataDir, "split.json"), JSON.stringify(split, null, 2), "utf8");
  await writeFile(path.join(metadataDir, "sources.csv"), sourceRows.join("\n"), "utf8");

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", "model/training/plan-phase1-collection.ts"],
      {
        cwd: path.resolve("."),
        env: { ...process.env, DATASET_ROOT: datasetRoot },
        stdio: "ignore",
      }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 0);
  const persisted = JSON.parse(
    await readFile(path.join(metadataDir, "phase1-collection-plan.json"), "utf8")
  ) as { ok: boolean; priorities: Array<{ status: string; id: string }> };
  assert.equal(persisted.ok, true);
  assert.equal(persisted.priorities.length, 1);
  assert.equal(persisted.priorities[0]?.id, "phase1-ready");
  assert.equal(persisted.priorities[0]?.status, "done");
  assert.equal(
    (persisted.priorities[0] as { title?: string })?.title,
    "Phase 1 数据集门槛已满足"
  );
});
