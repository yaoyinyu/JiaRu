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

async function createDebugImportFixture(options?: {
  confidence?: "high" | "medium" | "low";
  source?: "manual" | "model" | "saliency" | "mediapipe";
}) {
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
        modelBackend: "fallback",
        elapsedMs: 42,
        workerElapsedMs: 31,
        recognitionOptions: {
          maxCandidates: 8,
          workerTimeoutMs: 12000,
          includeLowConfidenceCandidates: true,
        },
        warnings: ["worker_unavailable_used_main_thread"],
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
            confidence: options?.confidence ?? "high",
            source: options?.source ?? "manual",
            hasMask: false,
            warnings: ["highlight_hotspots"],
            extractionDiagnostics: {
              qualityWarnings: ["mask_crop_touches_edge"],
              qualityOk: false,
              highlightPixels: 6,
              repairedPixels: 4,
              highlightRatio: 0.12,
            },
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
              warnings: ["highlight_hotspots"],
              extractionDiagnostics: {
                qualityWarnings: ["mask_crop_touches_edge"],
                qualityOk: false,
                highlightPixels: 5,
                repairedPixels: 3,
                highlightRatio: 0.08,
              },
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

async function createPrioritizedBatchDebugImportFixture() {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-debug-priority-import-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });
  const sampleDir = path.join(datasetRoot, "samples");
  const imageDir = path.join(datasetRoot, "images-src");
  await mkdir(sampleDir, { recursive: true });
  await mkdir(imageDir, { recursive: true });

  const sampleDefs = [
    {
      stem: "sample-high",
      extension: ".png",
      imageId: "local-debug-high",
      priorityTier: "high",
      priorityScore: 9,
      correctedCandidates: [],
    },
    {
      stem: "sample-medium",
      extension: ".jpg",
      imageId: "local-debug-medium",
      priorityTier: "medium",
      priorityScore: 5,
      correctedCandidates: [
        {
          id: "n1",
          cx: 100,
          cy: 70,
          angle: 0.15,
          length: 60,
          width: 28,
          assignedFinger: 1,
          confidence: "high",
          hasMask: false,
          warnings: [],
        },
      ],
    },
    {
      stem: "sample-low",
      extension: ".webp",
      imageId: "local-debug-low",
      priorityTier: "low",
      priorityScore: 1,
      correctedCandidates: [
        {
          id: "n1",
          cx: 180,
          cy: 96,
          angle: 0.15,
          length: 60,
          width: 28,
          assignedFinger: 3,
          confidence: "high",
          hasMask: false,
          warnings: [],
        },
      ],
    },
  ] as const;

  const ranked: Array<{
    samplePath: string;
    imageId: string;
    priorityTier: "high" | "medium" | "low";
    priorityScore: number;
  }> = [];

  for (const def of sampleDefs) {
    const builder = sharp({
      create: {
        width: 320,
        height: 200,
        channels: 3,
        background: { r: 240, g: 180, b: 200 },
      },
    });
    const imagePath = path.join(imageDir, `${def.stem}${def.extension}`);
    if (def.extension === ".jpg") {
      await builder.jpeg().toFile(imagePath);
    } else if (def.extension === ".webp") {
      await builder.webp().toFile(imagePath);
    } else {
      await builder.png().toFile(imagePath);
    }

    const samplePath = path.join(sampleDir, `${def.stem}.json`);
    await writeFile(
      samplePath,
      JSON.stringify(
        {
          imageId: def.imageId,
          imageUrl: "blob:demo",
          image: { width: 320, height: 200 },
          backend: "model",
          modelVersion: "nail-texture-seg-v2",
          warnings: [],
          originalCandidates: [],
          correctedCandidates: def.correctedCandidates,
          createdAt: "2026-06-30T12:34:56.000Z",
        },
        null,
        2
      ),
      "utf8"
    );
    ranked.push({
      samplePath,
      imageId: def.imageId,
      priorityTier: def.priorityTier,
      priorityScore: def.priorityScore,
    });
  }

  const priorityReportPath = path.join(datasetRoot, "priority-report.json");
  await writeFile(
    priorityReportPath,
    JSON.stringify(
      {
        ok: true,
        sampleCount: ranked.length,
        returnedCount: ranked.length,
        ranked,
      },
      null,
      2
    ),
    "utf8"
  );

  return {
    datasetRoot,
    sampleDir,
    imageDir,
    priorityReportPath,
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
  assert.equal(annotation.image.debug?.detectionBackend, "fallback");
  assert.equal(annotation.image.debug?.modelVersion, "fallback-v0");
  assert.equal(annotation.image.debug?.modelBackend, "fallback");
  assert.equal(annotation.image.debug?.elapsedMs, 42);
  assert.equal(annotation.image.debug?.workerElapsedMs, 31);
  assert.deepEqual(annotation.image.debug?.recognitionOptions, {
    maxCandidates: 8,
    workerTimeoutMs: 12000,
    includeLowConfidenceCandidates: true,
  });
  assert.deepEqual(annotation.image.debug?.warnings, [
    "worker_unavailable_used_main_thread",
  ]);
  assert.equal(annotation.annotations.length, 1);
  assert.equal(annotation.annotations[0].attributes?.fingerHint, "index");
  assert.equal(annotation.annotations[0].attributes?.debug?.candidateId, "n1");
  assert.equal(annotation.annotations[0].attributes?.debug?.source, "manual");
  assert.equal(annotation.annotations[0].attributes?.debug?.confidence, "high");
  assert.deepEqual(annotation.annotations[0].attributes?.debug?.warnings, [
    "highlight_hotspots",
  ]);
  assert.equal(annotation.annotations[0].attributes?.debug?.extractionQualityOk, false);
  assert.deepEqual(
    annotation.annotations[0].attributes?.debug?.extractionQualityWarnings,
    ["mask_crop_touches_edge"]
  );
  assert.equal(annotation.annotations[0].attributes?.debug?.highlightPixels, 6);
  assert.equal(annotation.annotations[0].attributes?.debug?.repairedPixels, 4);

  const sources = parseSourceRecords(
    await readFile(summary.sourcesCsvPath, "utf8")
  );
  assert.equal(sources.length, 1);
  assert.equal(sources[0].originType, "user");
  assert.equal(sources[0].sourceGroup, "user-corrections-001");
  assert.equal(sources[0].annotationCount, 1);
});

test("import debug sample maps medium confidence to dataset quality 3", async () => {
  const { datasetRoot, samplePath, imagePath } = await createDebugImportFixture({
    confidence: "medium",
    source: "manual",
  });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/import-debug-sample.ts",
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
    outputs: Array<{
      annotationPath: string;
    }>;
  };
  const annotation = JSON.parse(
    await readFile(summary.outputs[0].annotationPath, "utf8")
  ) as Parameters<typeof auditAnnotationDocument>[0];

  assert.equal(annotation.annotations[0].attributes?.quality, 3);
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

test("batch import debug sample can prioritize and filter by priority report", async () => {
  const { datasetRoot, sampleDir, imageDir, priorityReportPath } =
    await createPrioritizedBatchDebugImportFixture();

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
      "--priority-report",
      priorityReportPath,
      "--min-priority",
      "medium",
      "--top",
      "1",
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
    priorityFilters: {
      reportPath: string | null;
      minPriorityTier: string | null;
      top: number | null;
    };
    outputs: Array<{
      samplePath: string;
      priorityTier: string | null;
      priorityScore: number | null;
      negative: boolean;
    }>;
    sourcesCsvPath: string;
  };
  assert.equal(summary.imported, 1);
  assert.equal(summary.priorityFilters.reportPath, priorityReportPath);
  assert.equal(summary.priorityFilters.minPriorityTier, "medium");
  assert.equal(summary.priorityFilters.top, 1);
  assert.equal(summary.outputs[0]?.priorityTier, "high");
  assert.equal(summary.outputs[0]?.priorityScore, 9);
  assert.equal(summary.outputs[0]?.negative, true);
  assert.ok(summary.outputs[0]?.samplePath.endsWith("sample-high.json"));

  const sources = parseSourceRecords(await readFile(summary.sourcesCsvPath, "utf8"));
  assert.equal(sources.length, 1);
  assert.equal(sources[0].fileName, "sample-high.png");
});
