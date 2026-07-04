import path from "node:path";
import process from "node:process";
import { readFile, stat, writeFile } from "node:fs/promises";

interface MetricsLike {
  split: "train" | "val" | "test";
  imgsz: number;
  box_map50: number;
  box_map: number;
  seg_map50: number;
  seg_map: number;
  dry_run: boolean;
}

interface ManifestLike {
  version: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  modelFile: string;
  labels: string[];
}

interface ReleaseInput {
  name: string;
  metricsPath: string;
  manifestPath: string;
  failureSummaryPath?: string;
}

interface FailureSummaryLike {
  categoryCounts?: Record<string, number>;
  derivedAnnotationBreakdown?: {
    subcategoryCounts?: Record<string, number>;
  };
  totals?: {
    derivedAnnotationFailures?: number;
    inferredRecordFailure?: number;
    csvRows?: number;
  };
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/compare-training-releases.ts --baseline-metrics <metrics.json> --baseline-manifest <manifest.json> --candidate-metrics <metrics.json> --candidate-manifest <manifest.json> [--baseline-failure-summary <summary.json>] [--candidate-failure-summary <summary.json>] [--min-seg-delta -0.02] [--min-box-delta -0.02]"
  );
}

const args = process.argv.slice(2);
let baselineMetricsPath = "";
let baselineManifestPath = "";
let candidateMetricsPath = "";
let candidateManifestPath = "";
let baselineFailureSummaryPath = "";
let candidateFailureSummaryPath = "";
let outputPath = "";
let minSegDelta = -0.02;
let minBoxDelta = -0.02;

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--baseline-metrics") baselineMetricsPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--baseline-manifest") baselineManifestPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--candidate-metrics") candidateMetricsPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--candidate-manifest") candidateManifestPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--baseline-failure-summary") baselineFailureSummaryPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--candidate-failure-summary") candidateFailureSummaryPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--output") outputPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--min-seg-delta") {
    minSegDelta = Number(args[++index]);
    if (!Number.isFinite(minSegDelta)) usage();
  } else if (arg === "--min-box-delta") {
    minBoxDelta = Number(args[++index]);
    if (!Number.isFinite(minBoxDelta)) usage();
  } else {
    usage();
  }
}

if (!baselineMetricsPath || !baselineManifestPath || !candidateMetricsPath || !candidateManifestPath) {
  usage();
}

async function loadRelease(input: ReleaseInput) {
  const metrics = JSON.parse(await readFile(input.metricsPath, "utf8")) as MetricsLike;
  const manifest = JSON.parse(await readFile(input.manifestPath, "utf8")) as ManifestLike;
  const modelPath = path.resolve(path.dirname(input.manifestPath), manifest.modelFile);
  const modelStat = await stat(modelPath);
  const failureSummary = input.failureSummaryPath
    ? (JSON.parse(await readFile(input.failureSummaryPath, "utf8")) as FailureSummaryLike)
    : null;

  return {
    ...input,
    metrics,
    manifest,
    failureSummary,
    modelPath,
    modelSizeBytes: modelStat.size,
    modelSizeMb: Number((modelStat.size / (1024 * 1024)).toFixed(4)),
  };
}

function delta(candidate: number, baseline: number) {
  return Number((candidate - baseline).toFixed(4));
}

function getCount(record: Record<string, number> | undefined, key: string) {
  return Number(record?.[key] ?? 0);
}

function buildFailureSummarySnapshot(summary: FailureSummaryLike | null) {
  if (!summary) return null;
  return {
    totals: {
      derivedAnnotationFailures: Number(summary.totals?.derivedAnnotationFailures ?? 0),
      inferredRecordFailure: Number(summary.totals?.inferredRecordFailure ?? 0),
      csvRows: Number(summary.totals?.csvRows ?? 0),
    },
    categoryCounts: summary.categoryCounts ?? {},
    derivedAnnotationSubcategoryCounts: summary.derivedAnnotationBreakdown?.subcategoryCounts ?? {},
  };
}

const baseline = await loadRelease({
  name: "baseline",
  metricsPath: baselineMetricsPath,
  manifestPath: baselineManifestPath,
  failureSummaryPath: baselineFailureSummaryPath || undefined,
});
const candidate = await loadRelease({
  name: "candidate",
  metricsPath: candidateMetricsPath,
  manifestPath: candidateManifestPath,
  failureSummaryPath: candidateFailureSummaryPath || undefined,
});

const segMap50Delta = delta(candidate.metrics.seg_map50, baseline.metrics.seg_map50);
const boxMap50Delta = delta(candidate.metrics.box_map50, baseline.metrics.box_map50);
const segMapDelta = delta(candidate.metrics.seg_map, baseline.metrics.seg_map);
const boxMapDelta = delta(candidate.metrics.box_map, baseline.metrics.box_map);
const modelSizeMbDelta = delta(candidate.modelSizeMb, baseline.modelSizeMb);
const baselineFailureSnapshot = buildFailureSummarySnapshot(baseline.failureSummary);
const candidateFailureSnapshot = buildFailureSummarySnapshot(candidate.failureSummary);
const postprocessFailureDelta =
  baselineFailureSnapshot && candidateFailureSnapshot
    ? delta(
        getCount(candidateFailureSnapshot.categoryCounts, "postprocess"),
        getCount(baselineFailureSnapshot.categoryCounts, "postprocess")
      )
    : null;
const highlightHotspotDelta =
  baselineFailureSnapshot && candidateFailureSnapshot
    ? delta(
        getCount(
          candidateFailureSnapshot.derivedAnnotationSubcategoryCounts,
          "postprocess/highlight_hotspots"
        ),
        getCount(
          baselineFailureSnapshot.derivedAnnotationSubcategoryCounts,
          "postprocess/highlight_hotspots"
        )
      )
    : null;

const regressions: string[] = [];
const improvements: string[] = [];
const warnings: string[] = [];

if (baseline.metrics.dry_run || candidate.metrics.dry_run) {
  regressions.push("comparison requires real evaluation metrics; dry-run metrics are not allowed");
}
if (baseline.metrics.split !== candidate.metrics.split) {
  warnings.push(`metric splits differ: baseline=${baseline.metrics.split}, candidate=${candidate.metrics.split}`);
}
if (baseline.metrics.imgsz !== candidate.metrics.imgsz) {
  warnings.push(`imgsz differs: baseline=${baseline.metrics.imgsz}, candidate=${candidate.metrics.imgsz}`);
}
if (baseline.manifest.inputSize !== candidate.manifest.inputSize) {
  warnings.push(
    `manifest inputSize differs: baseline=${baseline.manifest.inputSize}, candidate=${candidate.manifest.inputSize}`
  );
}
if (segMap50Delta < minSegDelta) {
  regressions.push(`seg_map50 regressed by ${segMap50Delta} (threshold ${minSegDelta})`);
} else if (segMap50Delta > 0) {
  improvements.push(`seg_map50 improved by ${segMap50Delta}`);
}
if (boxMap50Delta < minBoxDelta) {
  regressions.push(`box_map50 regressed by ${boxMap50Delta} (threshold ${minBoxDelta})`);
} else if (boxMap50Delta > 0) {
  improvements.push(`box_map50 improved by ${boxMap50Delta}`);
}
if (modelSizeMbDelta > 0) {
  warnings.push(`candidate model is larger by ${modelSizeMbDelta}MB`);
}
if (JSON.stringify(baseline.manifest.backendPreferences) !== JSON.stringify(candidate.manifest.backendPreferences)) {
  warnings.push("backendPreferences changed between releases");
}
if (JSON.stringify(baseline.manifest.labels) !== JSON.stringify(candidate.manifest.labels)) {
  warnings.push("manifest labels changed between releases");
}
if (baselineFailureSnapshot || candidateFailureSnapshot) {
  if (!baselineFailureSnapshot || !candidateFailureSnapshot) {
    warnings.push("failure summary comparison is partial because one release is missing a failure summary");
  } else {
    if (postprocessFailureDelta! > 0) {
      warnings.push(`candidate postprocess failure count increased by ${postprocessFailureDelta}`);
    } else if (postprocessFailureDelta! < 0) {
      improvements.push(`postprocess failure count decreased by ${Math.abs(postprocessFailureDelta!)}`);
    }
    if (highlightHotspotDelta! > 0) {
      warnings.push(`candidate highlight hotspot failures increased by ${highlightHotspotDelta}`);
    } else if (highlightHotspotDelta! < 0) {
      improvements.push(
        `highlight hotspot failures decreased by ${Math.abs(highlightHotspotDelta!)}`
      );
    }
  }
}

const summary = {
  ok: regressions.length === 0,
  baseline: {
    metricsPath: baseline.metricsPath,
    manifestPath: baseline.manifestPath,
    failureSummaryPath: baseline.failureSummaryPath ?? null,
    version: baseline.manifest.version,
    split: baseline.metrics.split,
    imgsz: baseline.metrics.imgsz,
    seg_map50: baseline.metrics.seg_map50,
    box_map50: baseline.metrics.box_map50,
    seg_map: baseline.metrics.seg_map,
    box_map: baseline.metrics.box_map,
    modelPath: baseline.modelPath,
    modelSizeMb: baseline.modelSizeMb,
    failureSummary: baselineFailureSnapshot,
  },
  candidate: {
    metricsPath: candidate.metricsPath,
    manifestPath: candidate.manifestPath,
    failureSummaryPath: candidate.failureSummaryPath ?? null,
    version: candidate.manifest.version,
    split: candidate.metrics.split,
    imgsz: candidate.metrics.imgsz,
    seg_map50: candidate.metrics.seg_map50,
    box_map50: candidate.metrics.box_map50,
    seg_map: candidate.metrics.seg_map,
    box_map: candidate.metrics.box_map,
    modelPath: candidate.modelPath,
    modelSizeMb: candidate.modelSizeMb,
    failureSummary: candidateFailureSnapshot,
  },
  deltas: {
    seg_map50: segMap50Delta,
    box_map50: boxMap50Delta,
    seg_map: segMapDelta,
    box_map: boxMapDelta,
    modelSizeMb: modelSizeMbDelta,
    postprocessFailures: postprocessFailureDelta,
    highlightHotspotFailures: highlightHotspotDelta,
  },
  regressions,
  improvements,
  warnings,
  nextSteps:
    regressions.length === 0
      ? [
          "Candidate release comparison passed. You can preserve this report alongside the release decision.",
        ]
      : [
          "Review the regressions. If they are unacceptable, keep the baseline model available for rollback.",
        ],
};

if (outputPath) {
  await writeFile(outputPath, JSON.stringify(summary, null, 2), "utf8");
}

console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) {
  process.exitCode = 1;
}
