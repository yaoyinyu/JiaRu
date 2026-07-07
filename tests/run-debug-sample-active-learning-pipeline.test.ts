import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import sharp from "sharp";

const execFileAsync = promisify(execFile);

async function createFixture() {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-debug-active-dataset-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });

  const sampleDir = await mkdtemp(path.join(os.tmpdir(), "nail-debug-active-samples-"));
  const imageDir = await mkdtemp(path.join(os.tmpdir(), "nail-debug-active-images-"));

  const entries = [
    {
      stem: "sample-high",
      extension: ".png",
      imageId: "local-debug-high",
      backend: "fallback",
      modelBackend: "fallback",
      elapsedMs: 0,
      warnings: ["onnx_runtime_not_loaded"],
      originalCandidates: [
        {
          id: "n1",
          cx: 120,
          cy: 80,
          angle: 0.2,
          length: 60,
          width: 26,
          assignedFinger: 1,
          confidence: "high",
          source: "saliency",
          hasMask: true,
          warnings: [],
        },
      ],
      correctedCandidates: [],
    },
    {
      stem: "sample-medium",
      extension: ".jpg",
      imageId: "local-debug-medium",
      backend: "model",
      modelBackend: "wasm",
      elapsedMs: 184,
      warnings: [],
      originalCandidates: [
        {
          id: "n1",
          cx: 100,
          cy: 70,
          angle: 0.15,
          length: 50,
          width: 22,
          assignedFinger: 1,
          confidence: "low",
          source: "model",
          hasMask: false,
          warnings: [],
        },
      ],
      correctedCandidates: [
        {
          id: "n1",
          cx: 120,
          cy: 90,
          angle: 0.15,
          length: 65,
          width: 28,
          assignedFinger: 1,
          confidence: "high",
          source: "model",
          hasMask: true,
          warnings: [],
        },
      ],
    },
  ] as const;

  for (const entry of entries) {
    const imagePath = path.join(imageDir, `${entry.stem}${entry.extension}`);
    const builder = sharp({
      create: {
        width: 320,
        height: 200,
        channels: 3,
        background: { r: 240, g: 180, b: 200 },
      },
    });
    if (entry.extension === ".jpg") {
      await builder.jpeg().toFile(imagePath);
    } else {
      await builder.png().toFile(imagePath);
    }

    await writeFile(
      path.join(sampleDir, `${entry.stem}.json`),
      JSON.stringify(
        {
          imageId: entry.imageId,
          imageUrl: "blob:demo",
          image: { width: 320, height: 200 },
          backend: entry.backend,
          modelVersion: entry.backend === "fallback" ? "fallback-v0" : "nail-texture-seg-v2",
          modelBackend: entry.modelBackend,
          elapsedMs: entry.elapsedMs,
          warnings: entry.warnings,
          originalCandidates: entry.originalCandidates,
          correctedCandidates: entry.correctedCandidates,
          createdAt: "2026-07-03T00:00:00.000Z",
        },
        null,
        2
      ),
      "utf8"
    );
  }

  return { datasetRoot, sampleDir, imageDir };
}

test("run-debug-sample-active-learning-pipeline prioritizes imports and runs dataset gates", async () => {
  const { datasetRoot, sampleDir, imageDir } = await createFixture();

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-debug-sample-active-learning-pipeline.ts",
      "--sample-dir",
      sampleDir,
      "--image-dir",
      imageDir,
      "--copy-image",
      "--min-priority",
      "medium",
      "--top",
      "1",
      "--origin-type",
      "user",
      "--origin-ref",
      "authorized debug corrections",
      "--license",
      "user-authorized-internal-training",
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    reportPath: string;
    priorityReportPath: string;
    artifacts?: {
      activeLearningReleaseTraceDraftPath?: string | null;
      activeLearningHandoffPath?: string | null;
    };
    steps: Array<{ name: string; ok: boolean; stdout?: unknown }>;
  };

  assert.equal(report.ok, true);
  assert.deepEqual(
    report.steps.map((step) => step.name),
    [
      "prioritize-debug-samples",
      "import-debug-sample",
      "sync-sources-csv",
      "audit-sources-csv",
      "split-dataset",
      "audit-labels",
      "convert-annotations",
      "audit-phase1-readiness",
      "plan-phase1-collection",
      "generate-first-batch-checklist",
      "build-active-learning-release-trace-draft",
      "build-debug-sample-active-learning-handoff",
    ]
  );
  assert.ok(report.steps.every((step) => step.ok));

  const priorityReport = JSON.parse(await readFile(report.priorityReportPath, "utf8")) as {
    returnedCount: number;
    ranked: Array<{ imageId: string }>;
    backendBreakdown: Record<string, number>;
    modelBackendBreakdown: Record<string, number>;
    correctedCandidateSourceBreakdown: Record<string, number>;
    warningBreakdown: Record<string, number>;
  };
  assert.equal(priorityReport.returnedCount, 1);
  assert.equal(priorityReport.ranked[0]?.imageId, "local-debug-high");
  assert.deepEqual(priorityReport.backendBreakdown, { fallback: 1, model: 1 });
  assert.deepEqual(priorityReport.modelBackendBreakdown, { fallback: 1, wasm: 1 });
  assert.deepEqual(priorityReport.correctedCandidateSourceBreakdown, { model: 1 });
  assert.deepEqual(priorityReport.warningBreakdown, { onnx_runtime_not_loaded: 1 });

  const importStep = report.steps.find((step) => step.name === "import-debug-sample") as {
    stdout?: { imported?: number; outputs?: Array<{ priorityTier?: string | null }> };
  };
  assert.equal(importStep.stdout?.imported, 1);
  assert.equal(importStep.stdout?.outputs?.[0]?.priorityTier, "high");

  const savedReport = JSON.parse(await readFile(report.reportPath, "utf8")) as { ok: boolean };
  assert.equal(savedReport.ok, true);

  assert.ok(report.artifacts?.activeLearningReleaseTraceDraftPath);
  assert.ok(report.artifacts?.activeLearningHandoffPath);

  const releaseTraceDraft = JSON.parse(
    await readFile(report.artifacts!.activeLearningReleaseTraceDraftPath!, "utf8")
  ) as {
    activeLearning: {
      importedSampleCount: number;
      importedByPriority: { high: number };
      prioritySummary: {
        backendBreakdown: Record<string, number>;
        modelBackendBreakdown: Record<string, number>;
        correctedCandidateSourceBreakdown: Record<string, number>;
        warningBreakdown: Record<string, number>;
      } | null;
      readinessSnapshot: { imageCountGate: { actual: number } | null } | null;
    };
  };
  assert.equal(releaseTraceDraft.activeLearning.importedSampleCount, 1);
  assert.equal(releaseTraceDraft.activeLearning.importedByPriority.high, 1);
  assert.deepEqual(releaseTraceDraft.activeLearning.prioritySummary?.backendBreakdown, {
    fallback: 1,
    model: 1,
  });
  assert.deepEqual(releaseTraceDraft.activeLearning.prioritySummary?.modelBackendBreakdown, {
    fallback: 1,
    wasm: 1,
  });
  assert.deepEqual(
    releaseTraceDraft.activeLearning.prioritySummary?.correctedCandidateSourceBreakdown,
    { model: 1 }
  );
  assert.deepEqual(releaseTraceDraft.activeLearning.prioritySummary?.warningBreakdown, {
    onnx_runtime_not_loaded: 1,
  });
  assert.equal(releaseTraceDraft.activeLearning.readinessSnapshot?.imageCountGate.actual, 1);

  const handoff = JSON.parse(
    await readFile(report.artifacts!.activeLearningHandoffPath!, "utf8")
  ) as {
    version: string;
    activeLearning: {
      importedSampleCount: number;
      prioritySummary: {
        backendBreakdown: Record<string, number>;
        modelBackendBreakdown: Record<string, number>;
        correctedCandidateSourceBreakdown: Record<string, number>;
        warningBreakdown: Record<string, number>;
      } | null;
    };
    governanceHints: { activeLearningPipelineReportPath: string; activeLearningReleaseTraceDraftPath: string };
  };
  assert.equal(handoff.version, "debug-sample-active-learning-handoff/v1");
  assert.equal(handoff.activeLearning.importedSampleCount, 1);
  assert.deepEqual(handoff.activeLearning.prioritySummary?.backendBreakdown, {
    fallback: 1,
    model: 1,
  });
  assert.deepEqual(handoff.activeLearning.prioritySummary?.modelBackendBreakdown, {
    fallback: 1,
    wasm: 1,
  });
  assert.deepEqual(handoff.activeLearning.prioritySummary?.correctedCandidateSourceBreakdown, {
    model: 1,
  });
  assert.deepEqual(handoff.activeLearning.prioritySummary?.warningBreakdown, {
    onnx_runtime_not_loaded: 1,
  });
  assert.equal(handoff.governanceHints.activeLearningPipelineReportPath, report.reportPath);

  const sourcesCsv = await readFile(path.join(datasetRoot, "metadata", "sources.csv"), "utf8");
  assert.match(sourcesCsv, /sample-high\.png/);
  assert.doesNotMatch(sourcesCsv, /sample-medium\.jpg/);

  const splitJson = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "split.json"), "utf8")
  ) as { train: string[]; val: string[]; test: string[] };
  assert.equal(splitJson.train.length + splitJson.val.length + splitJson.test.length, 1);
});
