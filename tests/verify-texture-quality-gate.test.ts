import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

const curvedPolygon = [
  { x: 20, y: 6 },
  { x: 35, y: 12 },
  { x: 42, y: 38 },
  { x: 32, y: 58 },
  { x: 18, y: 58 },
  { x: 8, y: 38 },
  { x: 10, y: 14 },
];

const roughRectanglePolygon = [
  { x: 8, y: 8 },
  { x: 42, y: 8 },
  { x: 42, y: 58 },
  { x: 8, y: 58 },
];

async function writeAnnotation(
  dirPath: string,
  fileName: string,
  annotations: Array<{
    warnings?: string[];
    extractionQualityOk?: boolean;
    extractionQualityWarnings?: string[];
    highlightPixels?: number;
    repairedPixels?: number;
    highlightRatio?: number;
    polygon?: Array<{ x: number; y: number }>;
  }>
) {
  await writeFile(
    path.join(dirPath, fileName),
    JSON.stringify(
      {
        image: { fileName: fileName.replace(/\.json$/, ".jpg") },
        annotations: annotations.map(({ polygon, ...debug }, index) => ({
          id: `n${index + 1}`,
          polygon: polygon ?? curvedPolygon,
          attributes: { debug },
        })),
      },
      null,
      2
    ),
    "utf8"
  );
}

test("verify-texture-quality-gate passes when directly usable rate contamination rate and shape preservation meet thresholds", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-texture-quality-gate-pass-"));
  const annotationDir = path.join(root, "annotations");
  const outputPath = path.join(root, "texture-quality-gate.json");
  await mkdir(annotationDir, { recursive: true });

  await writeAnnotation(annotationDir, "sample-001.json", [
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 1, repairedPixels: 1, highlightRatio: 0.05, warnings: [] },
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
  ]);

  const { stdout } = await execFileAsync(process.execPath, [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/verify-texture-quality-gate.ts",
    "--annotation-dir",
    annotationDir,
    "--output",
    outputPath,
  ], { cwd: path.resolve(".") });

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    thresholds: { maxRoughRectangleRate: number };
    totals: {
      candidatesWithDebug: number;
      directlyUsableCandidates: number;
      contaminatedCandidates: number;
      candidatesWithPolygon: number;
      roughRectangleCandidates: number;
    };
    rates: { directlyUsableRate: number | null; contaminationRate: number | null; roughRectangleRate: number | null };
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.thresholds.maxRoughRectangleRate, 0.15);
  assert.equal(summary.totals.candidatesWithDebug, 6);
  assert.equal(summary.totals.directlyUsableCandidates, 6);
  assert.equal(summary.totals.contaminatedCandidates, 0);
  assert.equal(summary.totals.candidatesWithPolygon, 6);
  assert.equal(summary.totals.roughRectangleCandidates, 0);
  assert.equal(summary.rates.directlyUsableRate, 1);
  assert.equal(summary.rates.contaminationRate, 0);
  assert.equal(summary.rates.roughRectangleRate, 0);

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});

test("verify-texture-quality-gate fails when usable rate is low contamination remains or masks collapse to rectangles", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-texture-quality-gate-fail-"));
  const annotationDir = path.join(root, "annotations");
  await mkdir(annotationDir, { recursive: true });

  await writeAnnotation(annotationDir, "sample-001.json", [
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [], polygon: roughRectanglePolygon },
    { extractionQualityOk: false, extractionQualityWarnings: ["dirty_mask_crop"], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [], polygon: roughRectanglePolygon },
    { extractionQualityOk: false, extractionQualityWarnings: ["mask_crop_touches_edge"], highlightPixels: 9, repairedPixels: 4, highlightRatio: 0.2, warnings: ["highlight_hotspots"], polygon: curvedPolygon },
  ]);

  try {
    await execFileAsync(process.execPath, [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-texture-quality-gate.ts",
      "--annotation-dir",
      annotationDir,
    ], { cwd: path.resolve(".") });
    assert.fail("expected texture quality gate to exit non-zero");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const summary = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      rates: { directlyUsableRate: number | null; contaminationRate: number | null; roughRectangleRate: number | null };
      totals: { roughRectangleCandidates: number };
      warningBreakdown: { qualityWarnings: Record<string, number> };
      warnings: string[];
      nextSteps: string[];
    };

    assert.equal(summary.ok, false);
    assert.equal(summary.rates.directlyUsableRate, 0.3333);
    assert.equal(summary.rates.contaminationRate, 0.3333);
    assert.equal(summary.rates.roughRectangleRate, 0.6667);
    assert.equal(summary.totals.roughRectangleCandidates, 2);
    assert.equal(summary.warningBreakdown.qualityWarnings.dirty_mask_crop, 1);
    assert.ok(summary.warnings.some((item) => item.includes("directly usable rate")));
    assert.ok(summary.warnings.some((item) => item.includes("contamination rate")));
    assert.ok(summary.warnings.some((item) => item.includes("rough rectangle polygon rate")));
    assert.ok(summary.nextSteps.some((item) => item.includes("粗糙矩形 polygon")));
  }
});
test("verify-texture-quality-gate fails when release evidence sample size is too small", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-texture-quality-gate-evidence-"));
  const annotationDir = path.join(root, "annotations");
  await mkdir(annotationDir, { recursive: true });

  await writeAnnotation(annotationDir, "sample-001.json", [
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
  ]);

  try {
    await execFileAsync(process.execPath, [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-texture-quality-gate.ts",
      "--annotation-dir",
      annotationDir,
      "--evidence-scope",
      "release-test-split",
      "--min-documents",
      "2",
      "--min-candidates-with-debug",
      "2",
      "--min-candidates-with-polygon",
      "2",
    ], { cwd: path.resolve(".") });
    assert.fail("expected undersized release evidence to exit non-zero");
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    const summary = JSON.parse(execError.stdout ?? "{}") as {
      ok: boolean;
      evidence: {
        ok: boolean;
        scope: string;
        representativeTestSplit: boolean;
        minDocuments: number;
        minCandidatesWithDebug: number;
        minCandidatesWithPolygon: number;
      };
      warnings: string[];
      nextSteps: string[];
    };

    assert.equal(summary.ok, false);
    assert.equal(summary.evidence.ok, false);
    assert.equal(summary.evidence.scope, "release-test-split");
    assert.equal(summary.evidence.representativeTestSplit, true);
    assert.equal(summary.evidence.minDocuments, 2);
    assert.equal(summary.evidence.minCandidatesWithDebug, 2);
    assert.equal(summary.evidence.minCandidatesWithPolygon, 2);
    assert.ok(summary.warnings.some((item) => item.includes("evidence document count")));
    assert.ok(summary.nextSteps.some((item) => item.includes("扩大验收样本")));
  }
});
