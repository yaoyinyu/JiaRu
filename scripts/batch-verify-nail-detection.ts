import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readdir, writeFile } from "node:fs/promises";

const execFileAsync = promisify(execFile);
const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp"]);
const SKIP_NAME_PATTERNS = [
  /-candidate-mask\./i,
  /-skin-mask\./i,
  /-detection-debug\./i,
  /-green-annotation\./i,
  /batch-verify-report\.json$/i,
];

interface CliOptions {
  imageDir: string;
  outputDir: string;
  prefix?: string;
}

interface BatchImageReport {
  fileName: string;
  imagePath: string;
  ok: boolean;
  exitCode: number;
  output?: string;
  candidateMaskOutput?: string;
  skinMaskOutput?: string;
  debugJsonOutput?: string;
  count?: number;
  backend?: string;
  warnings?: string[];
  error?: string;
}

function parseArgs(argv: string[]): CliOptions {
  let imageDir: string | undefined;
  let outputDir: string | undefined;
  let prefix: string | undefined;

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
  }

  if (!imageDir || !outputDir) {
    throw new Error(
      "Usage: node --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir <dir> --output-dir <dir> [--prefix <name>]"
    );
  }

  return { imageDir, outputDir, prefix };
}

async function collectImages(imageDir: string): Promise<string[]> {
  const entries = await readdir(imageDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((fileName) => IMAGE_EXTENSIONS.has(path.extname(fileName).toLowerCase()))
    .filter((fileName) => !SKIP_NAME_PATTERNS.some((pattern) => pattern.test(fileName)))
    .sort((a, b) => a.localeCompare(b));
}

async function runSingleImage(
  imagePath: string,
  outputDir: string,
  prefix?: string
): Promise<BatchImageReport> {
  const fileName = path.basename(imagePath);
  const filePrefix = prefix
    ? `${prefix}-${fileName.replaceAll(/[^a-z0-9._-]+/gi, "_")}`
    : fileName.replaceAll(/[^a-z0-9._-]+/gi, "_");

  try {
    const { stdout } = await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-nail-detection.ts",
        imagePath,
        "--output-dir",
        outputDir,
        "--prefix",
        filePrefix,
      ],
      {
        cwd: path.resolve("."),
        maxBuffer: 10 * 1024 * 1024,
      }
    );

    const result = JSON.parse(stdout) as {
      output: string;
      candidateMaskOutput: string;
      skinMaskOutput: string;
      debugJsonOutput: string;
      count: number;
      backend: string;
      warnings?: string[];
    };

    return {
      fileName,
      imagePath,
      ok: true,
      exitCode: 0,
      output: result.output,
      candidateMaskOutput: result.candidateMaskOutput,
      skinMaskOutput: result.skinMaskOutput,
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
          debugJsonOutput?: string;
          count?: number;
          backend?: string;
          warnings?: string[];
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
      output: parsed?.output,
      candidateMaskOutput: parsed?.candidateMaskOutput,
      skinMaskOutput: parsed?.skinMaskOutput,
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
  const imageNames = await collectImages(options.imageDir);
  if (imageNames.length === 0) {
    throw new Error(`No supported image files found in ${options.imageDir}`);
  }

  await mkdir(options.outputDir, { recursive: true });
  const images = imageNames.map((fileName) => path.join(options.imageDir, fileName));
  const results: BatchImageReport[] = [];

  for (const imagePath of images) {
    results.push(await runSingleImage(imagePath, options.outputDir, options.prefix));
  }

  const reportPath = path.join(
    options.outputDir,
    `${options.prefix ? `${options.prefix}-` : ""}batch-verify-report.json`
  );

  const report = {
    ok: results.every((item) => item.ok),
    imageDir: options.imageDir,
    outputDir: options.outputDir,
    reportPath,
    totalImages: results.length,
    successCount: results.filter((item) => item.ok).length,
    failureCount: results.filter((item) => !item.ok).length,
    results,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
