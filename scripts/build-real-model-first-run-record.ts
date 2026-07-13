import path from "node:path";
import process from "node:process";
import { readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import {
  validateRealModelFirstRunRecord,
  validateRealModelUiReviewRecord,
  type RealModelFirstRunRecord,
  type RealModelUiReviewRecord,
} from "../src/lib/nail-texture-recognition/first-run-record.ts";
import { buildNailDebugArtifactPaths } from "../src/lib/nail-texture-recognition/debug-artifacts.ts";

const execFileAsync = promisify(execFile);

interface CliOptions {
  manifestPath: string;
  imagePath: string;
  outputPath: string;
  debugOutputDir: string;
  debugPrefix: string;
  metricsPath?: string;
  dumpPath?: string;
  fixtureOutPath?: string;
  annotationPath?: string;
  uiReviewPath?: string;
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = {
    manifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    outputPath: path.resolve("model/fixtures/real-model-first-run-record.generated.json"),
    debugOutputDir: path.resolve("model/debug/real-model-first-run"),
    debugPrefix: "real-model",
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--manifest") options.manifestPath = path.resolve(argv[++index]);
    else if (arg === "--image") options.imagePath = path.resolve(argv[++index]);
    else if (arg === "--output") options.outputPath = path.resolve(argv[++index]);
    else if (arg === "--debug-output-dir") options.debugOutputDir = path.resolve(argv[++index]);
    else if (arg === "--debug-prefix") options.debugPrefix = argv[++index];
    else if (arg === "--metrics") options.metricsPath = path.resolve(argv[++index]);
    else if (arg === "--dump") options.dumpPath = path.resolve(argv[++index]);
    else if (arg === "--fixture-out") options.fixtureOutPath = path.resolve(argv[++index]);
    else if (arg === "--annotation") options.annotationPath = path.resolve(argv[++index]);
    else if (arg === "--ui-review") options.uiReviewPath = path.resolve(argv[++index]);
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/build-real-model-first-run-record.ts --image <image> [--manifest <manifest.json>] [--output <record.json>] [--debug-output-dir <dir>] [--debug-prefix <name>] [--metrics <metrics.json>] [--dump <dump.json>] [--fixture-out <fixture.json>] [--annotation <green-annotation-image>] [--ui-review <ui-review.json>]"
      );
    }
  }

  if (!options.imagePath) {
    throw new Error("image path is required via --image");
  }

  return options as CliOptions;
}

async function runJsonScript(scriptPath: string, args: string[]) {
  try {
    const { stdout } = await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", scriptPath, ...args],
      { cwd: path.resolve(".") }
    );
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch (error) {
    const execError = error as { stdout?: string };
    if (execError.stdout) {
      return JSON.parse(execError.stdout) as Record<string, unknown>;
    }
    throw error;
  }
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function toDims(value: unknown): number[][] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const dims = (item as { dims?: unknown }).dims;
      return Array.isArray(dims) ? dims.filter((cell): cell is number => typeof cell === "number") : null;
    })
    .filter((item): item is number[] => item !== null);
}

const options = parseArgs(process.argv.slice(2));
const readinessArgs = ["--manifest", options.manifestPath, "--image", options.imagePath, "--debug-output-dir", options.debugOutputDir, "--debug-prefix", options.debugPrefix];
if (options.dumpPath) readinessArgs.push("--dump", options.dumpPath);
if (options.fixtureOutPath) readinessArgs.push("--fixture-out", options.fixtureOutPath);
if (options.annotationPath) readinessArgs.push("--annotation", options.annotationPath);

const readiness = await runJsonScript("scripts/verify-real-model-readiness.ts", readinessArgs);
const browserArgs = ["--manifest", options.manifestPath];
if (options.metricsPath) browserArgs.push("--metrics", options.metricsPath);
if (options.fixtureOutPath) browserArgs.push("--fixture", options.fixtureOutPath);
else if (typeof readiness.fixturePath === "string" && readiness.fixturePath) browserArgs.push("--fixture", String(readiness.fixturePath));
const browserIntegration = await runJsonScript("scripts/verify-browser-integration.ts", browserArgs);

let uiReview: RealModelUiReviewRecord | null = null;
if (options.uiReviewPath) {
  uiReview = JSON.parse(await readFile(options.uiReviewPath, "utf8")) as RealModelUiReviewRecord;
  const uiValidation = validateRealModelUiReviewRecord(uiReview);
  if (!uiValidation.ok) {
    throw new Error(`invalid ui review record: ${uiValidation.errors.join("; ")}`);
  }
}

const artifact = readiness.artifact as Record<string, unknown>;
const imageVerify = readiness.imageVerify as Record<string, unknown> | null;
const fixtureVerify = readiness.fixtureVerify as Record<string, unknown> | null;
const debugOutputs = Array.isArray(imageVerify?.debugOutputs) ? imageVerify?.debugOutputs : [];
const artifactPaths = buildNailDebugArtifactPaths({
  inputPath: options.imagePath,
  outputDir: options.debugOutputDir,
  prefix: options.debugPrefix,
});

const decisionStatus: RealModelFirstRunRecord["decision"]["status"] =
  !(artifact.ok as boolean) || !(browserIntegration.ok as boolean)
    ? "blocked"
    : uiReview && uiReview.decision.status === "blocked"
      ? "blocked"
      : readiness.ok && browserIntegration.ok && (!uiReview || uiReview.decision.status === "pass")
        ? "pass"
        : "needs_adjustment";

const nextActions =
  decisionStatus === "pass"
    ? ["Record is complete. Continue with broader /ar-tryon regression and model rollout planning."]
    : decisionStatus === "blocked"
      ? ["Fix the blocking model artifact or browser integration issue, then rebuild this first-run record."]
      : ["Review debug outputs, UI notes, and candidate quality. Adjust postprocess or runtime wiring, then rerun."];

const record: RealModelFirstRunRecord = {
  version: "nail-real-model-first-run/v1",
  createdAt: new Date().toISOString(),
  model: {
    manifestPath: options.manifestPath,
    modelPath: String(artifact.modelPath ?? ""),
    version: String(artifact.version ?? ""),
    backendPreferences: toStringArray(artifact.backendPreferences),
    artifactOk: Boolean(artifact.ok),
  },
  input: {
    imagePath: options.imagePath,
    annotationPath: options.annotationPath ?? null,
    debugOutputDir: options.debugOutputDir,
    debugPrefix: options.debugPrefix,
  },
  readiness: {
    ok: Boolean(readiness.ok) && Boolean(browserIntegration.ok),
    fixtureVerified: fixtureVerify ? Boolean(fixtureVerify.ok) : null,
    imageVerified: imageVerify ? typeof imageVerify.count === "number" && imageVerify.count >= 4 : null,
    warnings: [
      ...toStringArray(readiness.nextSteps),
      ...toStringArray(browserIntegration.warnings),
    ],
  },
  outputs: {
    debugJsonPath: artifactPaths.debugJsonOutput,
    debugOverlayPath: artifactPaths.output,
    candidateMaskPath: artifactPaths.candidateMaskOutput,
    skinMaskPath: artifactPaths.skinMaskOutput,
    recognitionMaskPath: artifactPaths.recognitionMaskOutput,
    modelOutputDumpPath: artifactPaths.modelOutputDumpPath,
    fixturePath:
      typeof readiness.fixturePath === "string" ? readiness.fixturePath : options.fixtureOutPath ?? null,
  },
  observations: {
    backend:
      imageVerify && (imageVerify.backend === "model" || imageVerify.backend === "fallback")
        ? imageVerify.backend
        : "unknown",
    candidateCount: imageVerify && typeof imageVerify.count === "number" ? imageVerify.count : null,
    maxCenterError:
      imageVerify && typeof imageVerify.maxCenterError === "number"
        ? imageVerify.maxCenterError
        : null,
    outputNames: Array.isArray(debugOutputs)
      ? debugOutputs
          .map((item) => (item && typeof item === "object" ? (item as { name?: unknown }).name : null))
          .filter((item): item is string => typeof item === "string")
      : [],
    outputDims: toDims(debugOutputs),
    newWarnings: [
      ...toStringArray(imageVerify?.warnings),
      ...toStringArray(browserIntegration.errors),
    ],
    notes: uiReview?.notes ?? "",
  },
  decision: {
    status: decisionStatus,
    summary:
      uiReview?.decision.summary ??
      (decisionStatus === "pass"
        ? "Readiness, browser integration, and available UI evidence all passed."
        : decisionStatus === "blocked"
          ? "At least one blocking issue remains in artifact or browser integration."
          : "Core wiring is present, but further UI or postprocess adjustment is still required."),
    nextActions,
  },
};

const validation = validateRealModelFirstRunRecord(record);
if (!validation.ok) {
  throw new Error(`generated first run record is invalid: ${validation.errors.join("; ")}`);
}

await writeFile(options.outputPath, JSON.stringify(record, null, 2), "utf8");
console.log(
  JSON.stringify(
    {
      ok: true,
      outputPath: options.outputPath,
      decisionStatus: record.decision.status,
      readinessOk: record.readiness.ok,
      browserIntegrationOk: Boolean(browserIntegration.ok),
      uiReviewIncluded: uiReview !== null,
    },
    null,
    2
  )
);
