import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import sharp from "sharp";
import {
  auditAnnotationDocument,
  parseSourceRecords,
} from "../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

async function runScript(scriptPath: string, datasetRoot: string) {
  await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", scriptPath],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );
}

async function createDebugImportFixture() {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-debug-import-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });

  const samplePath = path.join(datasetRoot, "sample.json");
  const imagePath = path.join(datasetRoot, "source-image.png");
  await sharp({
    create: {
      width: 320,
      height: 200,
      channels: 3,
      background: { r: 240, g: 180, b: 200 },
    },
  })
    .png()
    .toFile(imagePath);

  await writeFile(
    samplePath,
    JSON.stringify(
      {
        imageId: "local-debug-2026-06-30T12-34-56.000Z",
        imageUrl: "blob:demo",
        image: {
          width: 320,
          height: 200,
        },
        backend: "fallback",
        modelVersion: "fallback-v0",
        warnings: [],
        originalCandidates: [],
        correctedCandidates: [
          {
            id: "n1",
            cx: 120,
            cy: 80,
            angle: 0.2,
            length: 60,
            width: 28,
            assignedFinger: 1,
            confidence: "high",
            hasMask: false,
          },
        ],
        createdAt: "2026-06-30T12:34:56.000Z",
      },
      null,
      2
    ),
    "utf8"
  );

  return {
    datasetRoot,
    samplePath,
    imagePath,
  };
}

async function createBatchDebugImportFixture() {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-debug-batch-import-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });
  const sampleDir = path.join(datasetRoot, "samples");
  const imageDir = path.join(datasetRoot, "images-src");
  await mkdir(sampleDir, { recursive: true });
  await mkdir(imageDir, { recursive: true });

  for (const [stem, extension, cx, cy, finger] of [
    ["batch-001", ".png", 90, 70, 1],
    ["batch-002", ".jpg", 180, 96, 3],
  ] as const) {
    const builder = sharp({
      create: {
        width: 320,
        height: 200,
        channels: 3,
        background: { r: 240, g: 180, b: 200 },
      },
    });
    const outputPath = path.join(imageDir, `${stem}${extension}`);
    if (extension === ".jpg") {
      await builder.jpeg().toFile(outputPath);
    } else {
      await builder.png().toFile(outputPath);
    }

    await writeFile(
      path.join(sampleDir, `${stem}.json`),
      JSON.stringify(
        {
          imageId: `local-debug-${stem}`,
          imageUrl: "blob:demo",
          image: {
            width: 320,
            height: 200,
          },
          backend: "fallback",
          modelVersion: "fallback-v0",
          warnings: [],
          originalCandidates: [],
          correctedCandidates: [
            {
              id: "n1",
              cx,
              cy,
              angle: 0.15,
              length: 60,
              width: 28,
              assignedFinger: finger,
              confidence: "high",
              hasMask: false,
            },
          ],
          createdAt: "2026-06-30T12:34:56.000Z",
        },
        null,
        2
      ),
      "utf8"
    );
  }

  return {
    datasetRoot,
    sampleDir,
    imageDir,
  };
}

test("import debug sample converts corrected regions into dataset annotation", async () => {
  const { datasetRoot, samplePath, imagePath } = await createDebugImportFixture();

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/import-debug-sample.ts",
      "--copy-image",
      "--source-group",
      "user-corrections-001",
      samplePath,
      imagePath,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const summary = JSON.parse(stdout) as {
    imported: number;
    batchMode: boolean;
    outputs: Array<{
      annotationPath: string;
      copiedImage?: string;
      polygonCount: number;
      sourceGroup: string;
    }>;
    sourcesCsvPath: string;
  };
  assert.equal(summary.imported, 1);
  assert.equal(summary.batchMode, false);
  assert.equal(summary.outputs.length, 1);
  assert.equal(summary.outputs[0].polygonCount, 1);
  assert.equal(summary.outputs[0].sourceGroup, "user-corrections-001");
  assert.ok(summary.outputs[0].copiedImage);

  const annotation = JSON.parse(
    await readFile(summary.outputs[0].annotationPath, "utf8")
  ) as Parameters<typeof auditAnnotationDocument>[0];
  const audit = auditAnnotationDocument(annotation);
  assert.equal(audit.ok, true);
  assert.equal(annotation.image.fileName, "source-image.png");
  assert.equal(annotation.annotations.length, 1);
  assert.equal(annotation.annotations[0].attributes?.fingerHint, "index");

  const sources = parseSourceRecords(
    await readFile(summary.sourcesCsvPath, "utf8")
  );
  assert.equal(sources.length, 1);
  assert.equal(sources[0].originType, "user");
  assert.equal(sources[0].sourceGroup, "user-corrections-001");
  assert.equal(sources[0].annotationCount, 1);
});

test("imported debug sample flows through split audit and convert pipeline", async () => {
  const { datasetRoot, samplePath, imagePath } = await createDebugImportFixture();

  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/import-debug-sample.ts",
      "--copy-image",
      "--source-group",
      "user-corrections-002",
      samplePath,
      imagePath,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  await runScript("model/training/split-dataset.ts", datasetRoot);
  await runScript("model/training/audit-labels.ts", datasetRoot);
  await runScript("model/training/convert-annotations.ts", datasetRoot);

  const split = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "split.json"), "utf8")
  ) as { train: string[]; val: string[]; test: string[] };
  const entries = [
    ...split.train.map((fileName) => ["train", fileName] as const),
    ...split.val.map((fileName) => ["val", fileName] as const),
    ...split.test.map((fileName) => ["test", fileName] as const),
  ];
  assert.equal(entries.length, 1);
  assert.equal(entries[0][1], "source-image.png");

  const auditCsv = await readFile(
    path.join(datasetRoot, "metadata", "label-audit.csv"),
    "utf8"
  );
  assert.match(auditCsv, /source-image\.json/);
  assert.match(auditCsv, /true/);

  const labelPath = path.join(
    datasetRoot,
    "labels-yolo-seg",
    entries[0][0],
    "source-image.txt"
  );
  const labelContents = await readFile(labelPath, "utf8");
  assert.match(labelContents, /^0 /);
});

test("batch import debug sample imports all matching sample/image pairs", async () => {
  const { datasetRoot, sampleDir, imageDir } = await createBatchDebugImportFixture();

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/import-debug-sample.ts",
      "--copy-image",
      "--sample-dir",
      sampleDir,
      "--image-dir",
      imageDir,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const summary = JSON.parse(stdout) as {
    imported: number;
    batchMode: boolean;
    outputs: Array<{
      annotationPath: string;
      imagePath: string;
    }>;
    sourcesCsvPath: string;
  };
  assert.equal(summary.batchMode, true);
  assert.equal(summary.imported, 2);
  assert.equal(summary.outputs.length, 2);

  const annotations = await Promise.all(
    summary.outputs.map(async (item) =>
      JSON.parse(await readFile(item.annotationPath, "utf8")) as Parameters<
        typeof auditAnnotationDocument
      >[0]
    )
  );
  for (const annotation of annotations) {
    assert.equal(auditAnnotationDocument(annotation).ok, true);
  }

  const sources = parseSourceRecords(
    await readFile(summary.sourcesCsvPath, "utf8")
  );
  assert.equal(sources.length, 2);
  assert.deepEqual(
    sources.map((item) => item.fileName).sort(),
    ["batch-001.png", "batch-002.jpg"]
  );
});
