import path from "node:path";
import { readFile, readdir, writeFile } from "node:fs/promises";
import {
  validateIntakeBatchManifest,
  type NailTextureIntakeBatchManifest,
} from "../../src/lib/nail-texture-dataset.ts";

interface CliOptions {
  manifestPath: string;
  imageDir: string;
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

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(
    await readFile(options.manifestPath, "utf8")
  ) as NailTextureIntakeBatchManifest;

  const manifestValidation = validateIntakeBatchManifest(manifest);
  const imageEntries = await readdir(options.imageDir, { withFileTypes: true });
  const imageNames = new Set(
    imageEntries.filter((entry) => entry.isFile()).map((entry) => entry.name)
  );

  const manifestFiles = manifest.items.map((item) => item.fileName);
  const missingFiles = manifestFiles.filter((fileName) => !imageNames.has(fileName));
  const unlistedFiles = [...imageNames].filter((fileName) => !manifestFiles.includes(fileName));

  const report = {
    manifestPath: options.manifestPath,
    imageDir: options.imageDir,
    reportPath: path.join(
      path.dirname(options.manifestPath),
      `${path.basename(options.manifestPath, path.extname(options.manifestPath))}.report.json`
    ),
    ok: manifestValidation.ok && missingFiles.length === 0,
    sourceGroup: manifest.sourceGroup,
    originType: manifest.originType,
    itemCount: manifest.items.length,
    missingFiles,
    unlistedFiles,
    issues: [
      ...manifestValidation.issues,
      ...missingFiles.map((fileName) => ({
        code: "missing_image_file",
        severity: "error" as const,
        message: `image file is declared in manifest but missing on disk: ${fileName}`,
        fileName,
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
