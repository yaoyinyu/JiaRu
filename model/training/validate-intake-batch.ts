import path from "node:path";
import { readFile, readdir, writeFile } from "node:fs/promises";
import sharp from "sharp";
import {
  validateIntakeBatchManifest,
  type NailTextureIntakeBatchManifest,
} from "../../src/lib/nail-texture-dataset.ts";

interface CliOptions {
  manifestPath: string;
  imageDir: string;
}

interface ImageFileCheck {
  fileName: string;
  ok: boolean;
  width?: number;
  height?: number;
  format?: string;
  channels?: number;
  error?: string;
}

function parseArgs(argv: string[]): CliOptions {
  let manifestPath: string | undefined;
  let imageDir: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--manifest") {
      manifestPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--image-dir") {
      imageDir = path.resolve(argv[++index]);
      continue;
    }
  }

  if (!manifestPath || !imageDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/validate-intake-batch.ts --manifest <manifest.json> --image-dir <dir>"
    );
  }

  return { manifestPath, imageDir };
}

function normalizeManifestFileName(fileName: string): string {
  return fileName.replaceAll("\\", "/");
}

function isSafeRelativeImagePath(fileName: string): boolean {
  const normalized = normalizeManifestFileName(fileName).trim();
  if (!normalized) return false;
  if (path.isAbsolute(normalized)) return false;
  return !normalized.split("/").some((part) => part === ".." || part === "");
}

async function collectRelativeFiles(rootDir: string): Promise<string[]> {
  const files: string[] = [];

  async function walk(currentDir: string) {
    const entries = await readdir(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const absolutePath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await walk(absolutePath);
        continue;
      }
      if (!entry.isFile()) continue;
      files.push(path.relative(rootDir, absolutePath).replaceAll("\\", "/"));
    }
  }

  await walk(rootDir);
  return files.sort((a, b) => a.localeCompare(b));
}

async function inspectImageFile(imageDir: string, fileName: string): Promise<ImageFileCheck> {
  try {
    const safeFileName = normalizeManifestFileName(fileName);
    const metadata = await sharp(path.join(imageDir, safeFileName)).metadata();
    const width = metadata.width ?? 0;
    const height = metadata.height ?? 0;
    const ok = width > 0 && height > 0;
    return {
      fileName: safeFileName,
      ok,
      width,
      height,
      format: metadata.format,
      channels: metadata.channels,
      error: ok ? undefined : "image_has_no_dimensions",
    };
  } catch (error) {
    return {
      fileName,
      ok: false,
      error: error instanceof Error ? error.message : "image_decode_failed",
    };
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(
    await readFile(options.manifestPath, "utf8")
  ) as NailTextureIntakeBatchManifest;

  const manifestValidation = validateIntakeBatchManifest(manifest);
  const imageNames = new Set(await collectRelativeFiles(options.imageDir));

  const manifestFiles = manifest.items.map((item) => normalizeManifestFileName(item.fileName));
  const unsafeFiles = manifestFiles.filter((fileName) => !isSafeRelativeImagePath(fileName));
  const safeManifestFiles = manifestFiles.filter(isSafeRelativeImagePath);
  const missingFiles = safeManifestFiles.filter((fileName) => !imageNames.has(fileName));
  const unlistedFiles = [...imageNames].filter((fileName) => !manifestFiles.includes(fileName));
  const imageChecks = await Promise.all(
    safeManifestFiles
      .filter((fileName) => imageNames.has(fileName))
      .map((fileName) => inspectImageFile(options.imageDir, fileName))
  );
  const invalidImageFiles = imageChecks.filter((check) => !check.ok);

  const report = {
    manifestPath: options.manifestPath,
    imageDir: options.imageDir,
    reportPath: path.join(
      path.dirname(options.manifestPath),
      `${path.basename(options.manifestPath, path.extname(options.manifestPath))}.report.json`
    ),
    ok:
      manifestValidation.ok &&
      unsafeFiles.length === 0 &&
      missingFiles.length === 0 &&
      invalidImageFiles.length === 0,
    sourceGroup: manifest.sourceGroup,
    originType: manifest.originType,
    itemCount: manifest.items.length,
    missingFiles,
    unsafeFiles,
    unlistedFiles,
    invalidImageFiles: invalidImageFiles.map((check) => check.fileName),
    imageChecks,
    issues: [
      ...manifestValidation.issues,
      ...unsafeFiles.map((fileName) => ({
        code: "unsafe_image_path",
        severity: "error" as const,
        message: `image file path must be relative and cannot contain empty segments or ..: ${fileName}`,
        fileName,
      })),
      ...missingFiles.map((fileName) => ({
        code: "missing_image_file",
        severity: "error" as const,
        message: `image file is declared in manifest but missing on disk: ${fileName}`,
        fileName,
      })),
      ...invalidImageFiles.map((check) => ({
        code: "invalid_image_file",
        severity: "error" as const,
        message: `image file exists but cannot be decoded as a valid image: ${check.fileName}`,
        fileName: check.fileName,
        detail: check.error,
      })),
      ...unlistedFiles.map((fileName) => ({
        code: "unlisted_image_file",
        severity: "warning" as const,
        message: `image file exists on disk but is not listed in manifest: ${fileName}`,
        fileName,
      })),
    ],
  };

  await writeFile(report.reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
