import path from "node:path";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import type { NailDetectionGroundTruthFixture } from "../src/lib/nail-detection-fixture.ts";

const execFileAsync = promisify(execFile);
const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp"]);
const SKIP_NAME_PATTERNS = [
  /-candidate-mask\./i,
  /-skin-mask\./i,
  /-recognition-mask-overlay\./i,
  /-detection-debug\./i,
  /-green-annotation\./i,
  /batch-verify-report\.json$/i,
];

interface CliOptions {
  imageDir: string;
  outputDir: string;
  prefix?: string;
  fixtureDir?: string;
}

interface BatchImageReport {
  fileName: string;
  imagePath: string;
  ok: boolean;
  exitCode: number;
  fixturePath?: string | null;
  output?: string;
  candidateMaskOutput?: string;
  skinMaskOutput?: string;
  recognitionMaskOutput?: string;
  debugJsonOutput?: string;
  count?: number;
  backend?: string;
  warnings?: string[];
  error?: string;
}

interface FixtureIndexEntry {
  filePath: string;
  fixture: NailDetectionGroundTruthFixture;
}

function parseArgs(argv: string[]): CliOptions {
  let imageDir: string | undefined;
  let outputDir: string | undefined;
  let prefix: string | undefined;
  let fixtureDir: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--image-dir") {
      imageDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--output-dir") {
      outputDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--prefix") {
      prefix = argv[++index];
      continue;
    }
    if (arg === "--fixture-dir") {
      fixtureDir = path.resolve(argv[++index]);
      continue;
    }
  }

  if (!imageDir || !outputDir) {
    throw new Error(
      "Usage: node --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir <dir> --output-dir <dir> [--prefix <name>] [--fixture-dir <dir>]"
    );
  }

  return { imageDir, outputDir, prefix, fixtureDir };
}

async function collectCandidateImageNames(imageDir: string): Promise<string[]> {
  const entries = await readdir(imageDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((fileName) => IMAGE_EXTENSIONS.has(path.extname(fileName).toLowerCase()))
    .filter((fileName) => !SKIP_NAME_PATTERNS.some((pattern) => pattern.test(fileName)))
    .sort((a, b) => a.localeCompare(b));
}

async function loadFixtureIndex(fixtureDir?: string): Promise<FixtureIndexEntry[]> {
  if (!fixtureDir) return [];
  const entries = await readdir(fixtureDir, { withFileTypes: true });
  const fixtures: FixtureIndexEntry[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || path.extname(entry.name).toLowerCase() !== ".json") continue;
    const filePath = path.join(fixtureDir, entry.name);
    try {
      const fixture = JSON.parse(
        await readFile(filePath, "utf8")
      ) as NailDetectionGroundTruthFixture;
      if (fixture?.version === "nail-detection-fixture/v1" && typeof fixture.imagePath === "string") {
        fixtures.push({ filePath, fixture });
      }
    } catch {
      // Ignore unrelated JSON files in the fixture directory.
    }
  }

  return fixtures;
}

function stem(fileName: string): string {
  return path.basename(fileName, path.extname(fileName)).toLowerCase();
}

function buildAnnotationSkipSet(fixtures: FixtureIndexEntry[]): Set<string> {
  const skipNames = new Set<string>();

  for (const { fixture } of fixtures) {
    if (typeof fixture.annotationPath !== "string" || fixture.annotationPath.trim().length === 0) {
      continue;
    }
    skipNames.add(path.basename(fixture.annotationPath).toLowerCase());
  }

  return skipNames;
}

function splitImagesAndSkippedAnnotations(
  fileNames: string[],
  annotationSkipNames: Set<string>
): { imageNames: string[]; skippedAnnotationFiles: string[] } {
  const imageNames: string[] = [];
  const skippedAnnotationFiles: string[] = [];

  for (const fileName of fileNames) {
    if (annotationSkipNames.has(fileName.toLowerCase())) {
      skippedAnnotationFiles.push(fileName);
      continue;
    }
    imageNames.push(fileName);
  }

  return { imageNames, skippedAnnotationFiles };
}

function findMatchingFixture(
  imagePath: string,
  fixtures: FixtureIndexEntry[]
): FixtureIndexEntry | null {
  const fileName = path.basename(imagePath).toLowerCase();
  const imageStem = stem(imagePath);

  return (
    fixtures.find(({ fixture }) => path.basename(fixture.imagePath).toLowerCase() === fileName) ??
    fixtures.find(({ fixture }) => stem(fixture.imagePath) === imageStem) ??
    null
  );
}

async function runSingleImage(
  imagePath: string,
  outputDir: string,
  prefix?: string,
  fixture?: FixtureIndexEntry | null
): Promise<BatchImageReport> {
  const fileName = path.basename(imagePath);
  const fileDigest = createHash("sha256").update(fileName).digest("hex").slice(0, 12);
  const filePrefix = prefix ? `${prefix}-${fileDigest}` : fileDigest;

  const args = [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/verify-nail-detection.ts",
    imagePath,
    "--output-dir",
    outputDir,
    "--prefix",
    filePrefix,
  ];
  if (fixture) {
    args.push("--fixture", fixture.filePath);
  }

  try {
    const { stdout } = await execFileAsync(process.execPath, args, {
      cwd: path.resolve("."),
      maxBuffer: 10 * 1024 * 1024,
    });

    const result = JSON.parse(stdout) as {
      output: string;
      candidateMaskOutput: string;
      skinMaskOutput: string;
      recognitionMaskOutput: string;
      debugJsonOutput: string;
      count: number;
      backend: string;
      warnings?: string[];
      fixturePath?: string | null;
    };

    return {
      fileName,
      imagePath,
      ok: true,
      exitCode: 0,
      fixturePath: result.fixturePath ?? fixture?.filePath ?? null,
      output: result.output,
      candidateMaskOutput: result.candidateMaskOutput,
      skinMaskOutput: result.skinMaskOutput,
      recognitionMaskOutput: result.recognitionMaskOutput,
      debugJsonOutput: result.debugJsonOutput,
      count: result.count,
      backend: result.backend,
      warnings: result.warnings ?? [],
    };
  } catch (error) {
    const execError = error as Error & {
      code?: number;
      stdout?: string;
      stderr?: string;
    };
    let parsed:
      | {
          output?: string;
          candidateMaskOutput?: string;
          skinMaskOutput?: string;
          recognitionMaskOutput?: string;
          debugJsonOutput?: string;
          count?: number;
          backend?: string;
          warnings?: string[];
          fixturePath?: string | null;
        }
      | undefined;
    try {
      parsed = execError.stdout ? JSON.parse(execError.stdout) : undefined;
    } catch {
      parsed = undefined;
    }

    return {
      fileName,
      imagePath,
      ok: false,
      exitCode: typeof execError.code === "number" ? execError.code : 1,
      fixturePath: parsed?.fixturePath ?? fixture?.filePath ?? null,
      output: parsed?.output,
      candidateMaskOutput: parsed?.candidateMaskOutput,
      skinMaskOutput: parsed?.skinMaskOutput,
      recognitionMaskOutput: parsed?.recognitionMaskOutput,
      debugJsonOutput: parsed?.debugJsonOutput,
      count: parsed?.count,
      backend: parsed?.backend,
      warnings: parsed?.warnings ?? [],
      error: execError.stderr?.trim() || execError.message,
    };
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  await mkdir(options.outputDir, { recursive: true });

  const fixtures = await loadFixtureIndex(options.fixtureDir);
  const candidateImageNames = await collectCandidateImageNames(options.imageDir);
  const { imageNames, skippedAnnotationFiles } = splitImagesAndSkippedAnnotations(
    candidateImageNames,
    buildAnnotationSkipSet(fixtures)
  );

  if (imageNames.length === 0) {
    const reason = skippedAnnotationFiles.length > 0
      ? `No source images left after skipping ${skippedAnnotationFiles.length} annotation image(s) in ${options.imageDir}`
      : `No supported image files found in ${options.imageDir}`;
    throw new Error(reason);
  }

  const images = imageNames.map((fileName) => path.join(options.imageDir, fileName));
  const results: BatchImageReport[] = [];

  for (const imagePath of images) {
    const fixture = findMatchingFixture(imagePath, fixtures);
    results.push(await runSingleImage(imagePath, options.outputDir, options.prefix, fixture));
  }

  const reportPath = path.join(
    options.outputDir,
    `${options.prefix ? `${options.prefix}-` : ""}batch-verify-report.json`
  );

  const report = {
    ok: results.every((item) => item.ok),
    imageDir: options.imageDir,
    outputDir: options.outputDir,
    fixtureDir: options.fixtureDir ?? null,
    reportPath,
    totalImages: results.length,
    successCount: results.filter((item) => item.ok).length,
    failureCount: results.filter((item) => !item.ok).length,
    matchedFixtureCount: results.filter((item) => item.fixturePath).length,
    skippedAnnotationCount: skippedAnnotationFiles.length,
    skippedAnnotationFiles,
    results,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
