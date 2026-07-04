import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import {
  parseSourceRecords,
  readAnnotationDocument,
  type NailTextureAnnotationDocument,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";
import {
  DEFAULT_DATASET_ROOT,
  buildPhase1ReadinessReport,
  phase1ReadinessPaths,
} from "./phase1-readiness-report.ts";

interface CliOptions {
  datasetRoot: string;
  top: number;
}

interface Split {
  train: string[];
  val: string[];
  test: string[];
}

interface ReviewCandidate {
  fileName: string;
  currentSplit: "train" | "val" | "test" | "missing";
  annotationCount: number;
  score: number;
  reasons: string[];
  reviewAction: "mark_complex_background" | "review_possible_negative";
  risk: "low" | "medium" | "high";
  suggestedCommand: string;
}

interface Phase1ReviewCandidateReport {
  ok: boolean;
  datasetRoot: string;
  generatedAt: string;
  readiness: {
    ok: boolean;
    testNegatives: number;
    testComplexBackground: number;
  };
  counts: {
    sources: number;
    complexBackgroundCandidates: number;
    possibleNegativeCandidates: number;
  };
  complexBackgroundCandidates: ReviewCandidate[];
  possibleNegativeCandidates: ReviewCandidate[];
  warnings: string[];
  nextSteps: string[];
  reportPath: string;
  csvPath: string;
}

const COMPLEX_KEYWORDS = [
  "animal",
  "barbed",
  "black",
  "butterfly",
  "checker",
  "chrome",
  "cosmic",
  "cyberpunk",
  "dark",
  "denim",
  "dragon",
  "floral",
  "foil",
  "galaxy",
  "geometric",
  "glitter",
  "holographic",
  "lace",
  "lightning",
  "marble",
  "metallic",
  "nebu",
  "newspaper",
  "tortoise",
  "vampir",
];

const LOW_CONFIDENCE_REVIEW_KEYWORDS = [
  "background",
  "flower",
  "petal",
  "skin",
  "plain",
  "blank",
  "object",
  "negative",
];

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    datasetRoot: path.resolve(process.env.DATASET_ROOT ?? DEFAULT_DATASET_ROOT),
    top: 12,
  };
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    const next = () => {
      const value = argv[++index];
      if (!value) throw new Error(`${arg} requires a value`);
      return value;
    };
    if (arg === "--dataset-root") options.datasetRoot = path.resolve(next());
    else if (arg === "--top") options.top = Number(next());
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!Number.isInteger(options.top) || options.top < 1) {
    throw new Error("--top must be a positive integer");
  }
  return options;
}

async function readSplit(splitPath: string): Promise<Split> {
  try {
    return JSON.parse(await readFile(splitPath, "utf8")) as Split;
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return { train: [], val: [], test: [] };
    throw error;
  }
}

async function readSources(sourcesCsvPath: string): Promise<SourceRecord[]> {
  try {
    return parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return [];
    throw error;
  }
}

function currentSplit(split: Split, fileName: string): ReviewCandidate["currentSplit"] {
  if (split.test.includes(fileName)) return "test";
  if (split.val.includes(fileName)) return "val";
  if (split.train.includes(fileName)) return "train";
  return "missing";
}

function keywordHits(text: string, keywords: string[]): string[] {
  const normalized = text.toLowerCase();
  return keywords.filter((keyword) => normalized.includes(keyword));
}

function markerCommand(fileName: string, args: string[]): string {
  return [
    "node --no-warnings --experimental-strip-types model/training/mark-phase1-samples.ts",
    "--file",
    JSON.stringify(fileName),
    ...args,
  ].join(" ");
}

function complexCandidate(
  record: SourceRecord,
  document: NailTextureAnnotationDocument,
  splitName: ReviewCandidate["currentSplit"]
): ReviewCandidate | undefined {
  const hits = keywordHits(`${record.fileName} ${record.notes}`, COMPLEX_KEYWORDS);
  if (hits.length === 0) return undefined;

  const score = hits.length * 10 + (splitName === "test" ? 5 : 0) + Math.min(document.annotations.length, 5);
  return {
    fileName: record.fileName,
    currentSplit: splitName,
    annotationCount: document.annotations.length,
    score,
    reasons: [
      `keyword hits: ${hits.join(", ")}`,
      splitName === "test" ? "already in test split" : `currently in ${splitName}; can be moved to test`,
    ],
    reviewAction: "mark_complex_background",
    risk: "low",
    suggestedCommand: markerCommand(record.fileName, [
      "--background",
      "mixed",
      "--reason",
      "complex_background",
      "--sample",
      "ai_generated",
      "--ensure-test",
    ]),
  };
}

function possibleNegativeCandidate(
  record: SourceRecord,
  document: NailTextureAnnotationDocument,
  splitName: ReviewCandidate["currentSplit"]
): ReviewCandidate | undefined {
  const hits = keywordHits(`${record.fileName} ${record.notes}`, LOW_CONFIDENCE_REVIEW_KEYWORDS);
  const annotationCount = document.annotations.length;
  if (annotationCount > 2 && hits.length === 0) return undefined;

  const score =
    (annotationCount === 0 ? 50 : annotationCount === 1 ? 30 : annotationCount === 2 ? 18 : 0) +
    hits.length * 4 +
    (splitName === "test" ? 3 : 0);
  const reasons = [
    annotationCount <= 2
      ? `low annotation count: ${annotationCount}`
      : "keyword-only weak signal; verify visually",
  ];
  if (hits.length > 0) reasons.push(`keyword hits: ${hits.join(", ")}`);

  return {
    fileName: record.fileName,
    currentSplit: splitName,
    annotationCount,
    score,
    reasons,
    reviewAction: "review_possible_negative",
    risk: annotationCount === 0 ? "medium" : "high",
    suggestedCommand:
      annotationCount === 0
        ? markerCommand(record.fileName, ["--negative", "true", "--clear-annotations", "--ensure-test"])
        : "Only run mark-phase1-samples with --negative true --clear-annotations after visual review confirms there is no valid nail-texture region.",
  };
}

function escapeCsv(value: string | number): string {
  const text = String(value);
  return /[,"\n]/.test(text) ? `"${text.replaceAll("\"", "\"\"")}"` : text;
}

function candidatesToCsv(candidates: ReviewCandidate[]): string {
  const rows = [
    [
      "reviewAction",
      "fileName",
      "currentSplit",
      "annotationCount",
      "score",
      "risk",
      "reasons",
      "suggestedCommand",
    ],
    ...candidates.map((candidate) => [
      candidate.reviewAction,
      candidate.fileName,
      candidate.currentSplit,
      candidate.annotationCount,
      candidate.score,
      candidate.risk,
      candidate.reasons.join("; "),
      candidate.suggestedCommand,
    ]),
  ];
  return `${rows.map((row) => row.map(escapeCsv).join(",")).join("\n")}\n`;
}

async function buildReport(options: CliOptions): Promise<Phase1ReviewCandidateReport> {
  const paths = phase1ReadinessPaths(options.datasetRoot);
  const split = await readSplit(paths.splitPath);
  const sources = await readSources(paths.sourcesCsvPath);
  const readiness = await buildPhase1ReadinessReport(options.datasetRoot);
  const complexCandidates: ReviewCandidate[] = [];
  const negativeCandidates: ReviewCandidate[] = [];

  for (const record of sources) {
    const annotationPath = path.join(options.datasetRoot, record.annotationPath);
    const document = await readAnnotationDocument(annotationPath);
    const splitName = currentSplit(split, record.fileName);
    const complex = complexCandidate(record, document, splitName);
    if (complex) complexCandidates.push(complex);
    const negative = possibleNegativeCandidate(record, document, splitName);
    if (negative) negativeCandidates.push(negative);
  }

  const sortCandidates = (a: ReviewCandidate, b: ReviewCandidate) =>
    b.score - a.score || a.fileName.localeCompare(b.fileName);
  const topComplex = complexCandidates.sort(sortCandidates).slice(0, options.top);
  const topNegative = negativeCandidates.sort(sortCandidates).slice(0, options.top);
  const metadataDir = paths.metadataDir;
  const reportPath = path.join(metadataDir, "phase1-review-candidates.json");
  const csvPath = path.join(metadataDir, "phase1-review-candidates.csv");
  const warnings: string[] = [];
  if (readiness.gates.testSplitHasNegative.ok === false) {
    warnings.push("test split still needs at least one visually confirmed negative sample");
  }
  if (readiness.gates.testSplitHasComplexBackground.ok === false) {
    warnings.push("test split still needs at least one visually confirmed complex-background sample");
  }
  if (topNegative.length === 0 || topNegative.every((candidate) => candidate.risk === "high")) {
    warnings.push("no safe automatic negative sample was found; collect or generate true no-nail/non-target negatives if review does not confirm one");
  }

  return {
    ok: true,
    datasetRoot: options.datasetRoot,
    generatedAt: new Date().toISOString(),
    readiness: {
      ok: readiness.ok,
      testNegatives: readiness.testCoverage.negatives,
      testComplexBackground: readiness.testCoverage.complexBackground,
    },
    counts: {
      sources: sources.length,
      complexBackgroundCandidates: complexCandidates.length,
      possibleNegativeCandidates: negativeCandidates.length,
    },
    complexBackgroundCandidates: topComplex,
    possibleNegativeCandidates: topNegative,
    warnings,
    nextSteps: [
      "Visually inspect the top complex-background candidates and run the suggested command for one confirmed sample.",
      "Only mark a negative sample after confirming the image has no valid nail-texture target; otherwise add dedicated negative images.",
      "After marking, rerun audit-phase1-readiness.ts and audit:mvp-readiness.",
    ],
    reportPath,
    csvPath,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const report = await buildReport(options);
  const csv = candidatesToCsv([
    ...report.complexBackgroundCandidates,
    ...report.possibleNegativeCandidates,
  ]);
  await mkdir(path.dirname(report.reportPath), { recursive: true });
  await writeFile(report.reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await writeFile(report.csvPath, csv, "utf8");
  console.log(JSON.stringify(report, null, 2));
}

await main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
