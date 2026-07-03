import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

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
  }>
) {
  await writeFile(
    path.join(dirPath, fileName),
    JSON.stringify(
      {
        image: { fileName: fileName.replace(/\.json$/, ".jpg") },
        annotations: annotations.map((debug, index) => ({
          id: `n${index + 1}`,
          attributes: { debug },
        })),
      },
      null,
      2
    ),
    "utf8"
  );
}

test("verify-texture-quality-gate passes when directly usable rate and contamination rate meet thresholds", async () => {
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
    totals: { candidatesWithDebug: number; directlyUsableCandidates: number; contaminatedCandidates: number };
    rates: { directlyUsableRate: number | null; contaminationRate: number | null };
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.totals.candidatesWithDebug, 6);
  assert.equal(summary.totals.directlyUsableCandidates, 6);
  assert.equal(summary.totals.contaminatedCandidates, 0);
  assert.equal(summary.rates.directlyUsableRate, 1);
  assert.equal(summary.rates.contaminationRate, 0);

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});

test("verify-texture-quality-gate fails when usable rate is low or contamination remains", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-texture-quality-gate-fail-"));
  const annotationDir = path.join(root, "annotations");
  await mkdir(annotationDir, { recursive: true });

  await writeAnnotation(annotationDir, "sample-001.json", [
    { extractionQualityOk: true, extractionQualityWarnings: [], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
    { extractionQualityOk: false, extractionQualityWarnings: ["dirty_mask_crop"], highlightPixels: 0, repairedPixels: 0, highlightRatio: 0, warnings: [] },
    { extractionQualityOk: false, extractionQualityWarnings: ["mask_crop_touches_edge"], highlightPixels: 9, repairedPixels: 4, highlightRatio: 0.2, warnings: ["highlight_hotspots"] },
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
      rates: { directlyUsableRate: number | null; contaminationRate: number | null };
      warningBreakdown: { qualityWarnings: Record<string, number> };
      warnings: string[];
    };

    assert.equal(summary.ok, false);
    assert.equal(summary.rates.directlyUsableRate, 0.3333);
    assert.equal(summary.rates.contaminationRate, 0.3333);
    assert.equal(summary.warningBreakdown.qualityWarnings.dirty_mask_crop, 1);
    assert.ok(summary.warnings.some((item) => item.includes("directly usable rate")));
    assert.ok(summary.warnings.some((item) => item.includes("contamination rate")));
  }
});
