import path from "node:path";
import { cp, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import {
  parseSourceRecords,
  stringifySourceRecords,
  upsertSourceRecord,
  type NailTextureAnnotationDocument,
  type NailTextureIntakeBatchManifest,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);
const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);

interface CliOptions {
  rootDir: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

interface JsonScriptResult {
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--root-dir") rootDir = path.resolve(argv[++index]);
  }
  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/import-reviewed-batch.ts --root-dir <seed-batch-dir>"
    );
  }
  return { rootDir };
}

async function runJsonScript(
  scriptPath: string,
  args: string[],
  env: NodeJS.ProcessEnv
): Promise<unknown> {
  const { stdout } = await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", scriptPath, ...args],
    {
      cwd: path.resolve("."),
      env,
    }
  );
  return JSON.parse(stdout);
}

async function runJsonScriptAllowFailure(
  scriptPath: string,
  args: string[],
  env: NodeJS.ProcessEnv
): Promise<JsonScriptResult> {
  try {
    return {
      ok: true,
      stdout: await runJsonScript(scriptPath, args, env),
    };
  } catch (error) {
    const execError = error as Error & { stdout?: string; stderr?: string };
    if (execError.stdout?.trim()) {
      try {
        return {
          ok: true,
          stdout: JSON.parse(execError.stdout),
          stderr: execError.stderr,
        };
      } catch {
        // Fall through to reporting the script failure.
      }
    }
    return {
      ok: false,
      stderr: execError.stderr || execError.message,
    };
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const selectedRoot = path.join(options.rootDir, "selected");
  const selectedImagesDir = path.join(selectedRoot, "images");
  const selectedAnnotationsDir = path.join(selectedRoot, "annotations", "raw-json");
  const manifestCandidates = (await readdir(selectedRoot))
    .filter((name) => name.endsWith(".manifest.json"))
    .sort();
  if (manifestCandidates.length === 0) {
    throw new Error(`No selected manifest found in ${selectedRoot}`);
  }
  const manifestPath = path.join(selectedRoot, manifestCandidates[0]);
  const manifest = JSON.parse(
    await readFile(manifestPath, "utf8")
  ) as NailTextureIntakeBatchManifest;

  const datasetImagesDir = path.join(datasetRoot, "images", "raw");
  const datasetAnnotationsDir = path.join(datasetRoot, "annotations", "raw-json");
  const metadataDir = path.join(datasetRoot, "metadata");
  const sourcesCsvPath = path.join(metadataDir, "sources.csv");
  const reportPath = path.join(
    metadataDir,
    `reviewed-import-${manifest.sourceGroup}.report.json`
  );

  await mkdir(datasetImagesDir, { recursive: true });
  await mkdir(datasetAnnotationsDir, { recursive: true });
  await mkdir(metadataDir, { recursive: true });

  const copiedImages: string[] = [];
  const copiedAnnotations: string[] = [];
  let sourceRecords: SourceRecord[] = [];
  try {
    sourceRecords = parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code !== "ENOENT") throw error;
  }
  const importedDocuments: Array<{
    fileName: string;
    annotationPath: string;
    imagePath: string;
    polygonCount: number;
  }> = [];

  for (const item of manifest.items) {
    const fileName = item.fileName;
    const imageId = fileName.replace(/\.[^.]+$/, "");
    const sourceImagePath = path.join(selectedImagesDir, fileName);
    const sourceAnnotationPath = path.join(selectedAnnotationsDir, `${imageId}.json`);
    const targetImagePath = path.join(datasetImagesDir, fileName);
    const targetAnnotationPath = path.join(datasetAnnotationsDir, `${imageId}.json`);

    await cp(sourceImagePath, targetImagePath);
    await cp(sourceAnnotationPath, targetAnnotationPath);
    copiedImages.push(fileName);
    copiedAnnotations.push(`${imageId}.json`);

    const document = JSON.parse(
      await readFile(targetAnnotationPath, "utf8")
    ) as NailTextureAnnotationDocument;
    const now = new Date().toISOString();
    sourceRecords = upsertSourceRecord(sourceRecords, {
      imageId: document.image.id,
      fileName,
      sourceGroup: manifest.sourceGroup,
      originType: manifest.originType,
      originRef: item.originRef?.trim() || manifest.defaultOriginRef,
      license: manifest.license,
      notes: item.notes?.trim() || "",
      negative: document.image.negative ?? false,
      annotationPath: path.relative(datasetRoot, targetAnnotationPath).replaceAll("\\", "/"),
      imagePath: path.relative(datasetRoot, targetImagePath).replaceAll("\\", "/"),
      annotationCount: document.annotations.length,
      createdAt: now,
      updatedAt: now,
    });
    importedDocuments.push({
      fileName,
      annotationPath: targetAnnotationPath,
      imagePath: targetImagePath,
      polygonCount: document.annotations.length,
    });
  }
  await writeFile(sourcesCsvPath, stringifySourceRecords(sourceRecords), "utf8");

  const baseEnv = {
    ...process.env,
    DATASET_ROOT: datasetRoot,
  };

  const report: {
    ok: boolean;
    rootDir: string;
    datasetRoot: string;
    sourceGroup: string;
    reportPath: string;
    copiedImages: string[];
    copiedAnnotations: string[];
    importedDocuments: typeof importedDocuments;
    steps: StepResult[];
    readinessSnapshot?: unknown;
  } = {
    ok: false,
    rootDir: options.rootDir,
    datasetRoot,
    sourceGroup: manifest.sourceGroup,
    reportPath,
    copiedImages,
    copiedAnnotations,
    importedDocuments,
    steps: [],
  };

  for (const step of [
    "sync-sources-csv.ts",
    "audit-sources-csv.ts",
    "split-dataset.ts",
    "audit-labels.ts",
    "convert-annotations.ts",
  ] as const) {
    try {
      const output = await runJsonScript(`model/training/${step}`, [], baseEnv);
      report.steps.push({
        name: step.replace(/\.ts$/, ""),
        ok: true,
        stdout: output,
      });
    } catch (error) {
      const execError = error as Error & { stderr?: string };
      report.steps.push({
        name: step.replace(/\.ts$/, ""),
        ok: false,
        stderr: execError.stderr || execError.message,
      });
      await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
  }

  const readiness = await runJsonScriptAllowFailure(
    "model/training/audit-phase1-readiness.ts",
    [],
    baseEnv
  );
  report.steps.push({
    name: "audit-phase1-readiness",
    ok: readiness.ok,
    stdout: readiness.stdout,
    stderr: readiness.stderr,
  });
  report.readinessSnapshot = readiness.stdout;
  if (!readiness.ok) {
    await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  const trainingDatasetReadiness = await runJsonScriptAllowFailure(
    "model/training/verify-training-dataset-readiness.ts",
    ["--dataset-root", datasetRoot],
    baseEnv
  );
  report.steps.push({
    name: "verify-training-dataset-readiness",
    ok: trainingDatasetReadiness.ok,
    stdout: trainingDatasetReadiness.stdout,
    stderr: trainingDatasetReadiness.stderr,
  });
  report.trainingDatasetReadinessSnapshot = trainingDatasetReadiness.stdout;
  if (!trainingDatasetReadiness.ok) {
    await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  report.ok = report.steps.every((step) => step.ok);
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
}

await main();
