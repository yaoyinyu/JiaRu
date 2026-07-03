import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFile } from "node:fs/promises";

const execFileAsync = promisify(execFile);

interface CliOptions {
  manifestPath: string;
  metricsPath?: string;
  fixturePath?: string;
  pickerPath: string;
  clientWorkerPath: string;
  workerPath: string;
  runtimePath: string;
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    manifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    pickerPath: path.resolve("src/components/NailArtPicker.tsx"),
    clientWorkerPath: path.resolve("src/lib/nail-texture-recognition/client-worker.ts"),
    workerPath: path.resolve("src/workers/nail-texture-recognition.worker.ts"),
    runtimePath: path.resolve("src/lib/nail-texture-recognition/model-runtime.ts"),
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--manifest") {
      options.manifestPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--metrics") {
      options.metricsPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--fixture") {
      options.fixturePath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--picker") {
      options.pickerPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--client-worker") {
      options.clientWorkerPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--worker") {
      options.workerPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--runtime") {
      options.runtimePath = path.resolve(argv[++index]);
      continue;
    }
    throw new Error(
      "Usage: node --experimental-strip-types scripts/verify-browser-integration.ts [--manifest <manifest.json>] [--metrics <metrics.json>] [--fixture <fixture.json>] [--picker <NailArtPicker.tsx>] [--client-worker <client-worker.ts>] [--worker <worker.ts>] [--runtime <model-runtime.ts>]"
    );
  }

  return options;
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
    const execError = error as { stdout?: string; message?: string };
    if (execError.stdout) {
      return JSON.parse(execError.stdout) as Record<string, unknown>;
    }
    throw error;
  }
}

function hasAll(text: string, patterns: RegExp[]): boolean {
  return patterns.every((pattern) => pattern.test(text));
}

const options = parseArgs(process.argv.slice(2));
const artifact = await runJsonScript("scripts/verify-model-artifact.ts", [options.manifestPath]);
const trainingRelease = options.metricsPath
  ? await runJsonScript("scripts/verify-training-release.ts", [
      "--metrics",
      options.metricsPath,
      "--manifest",
      options.manifestPath,
    ])
  : null;
const fixtureVerify = options.fixturePath
  ? await runJsonScript("scripts/verify-model-output-fixture.ts", [options.fixturePath])
  : null;

const pickerSource = await readFile(options.pickerPath, "utf8");
const clientWorkerSource = await readFile(options.clientWorkerPath, "utf8");
const workerSource = await readFile(options.workerPath, "utf8");
const runtimeSource = await readFile(options.runtimePath, "utf8");

const contractChecks = [
  {
    name: "picker_uses_worker_recognition",
    ok: hasAll(pickerSource, [/recognizeNailTexturesInWorker/, /preferModel:\s*true/]),
  },
  {
    name: "picker_surfaces_detection_summary",
    ok: hasAll(
      pickerSource,
      [
        /backend:\s*result\.backend/,
        /modelVersion:\s*result\.modelVersion/,
        /modelBackend:\s*result\.modelInfo\?\.backend/,
        /elapsedMs:\s*result\.elapsedMs/,
        /warnings:\s*result\.warnings/,
      ]
    ),
  },
  {
    name: "client_worker_passes_manifest_and_prefer_model",
    ok: hasAll(clientWorkerSource, [/new Worker\(/, /preferModel:\s*options\.preferModel \?\? true/, /manifestUrl:\s*options\.manifestUrl/]),
  },
  {
    name: "worker_calls_recognition_and_posts_response",
    ok: hasAll(
      workerSource,
      [
        /recognizeNailTextures\(/,
        /self\.postMessage\(response\)/,
        /manifestUrl:\s*request\.manifestUrl/,
        /modelInfo:\s*result\.modelInfo/,
      ]
    ),
  },
  {
    name: "runtime_loads_manifest_and_selects_execution_provider",
    ok: hasAll(runtimeSource, [/loadNailTextureModelManifest/, /createOrtSession/, /resolveOrtExecutionProviders/]),
  },
];

const errors = [
  ...(!(artifact.ok as boolean) ? [String((artifact.errors as unknown[]).join("; "))] : []),
  ...contractChecks.filter((check) => !check.ok).map((check) => `browser contract check failed: ${check.name}`),
  ...(trainingRelease && !trainingRelease.ok
    ? [`training release gate failed: ${String((trainingRelease.errors as unknown[]).join("; "))}`]
    : []),
  ...(fixtureVerify && !fixtureVerify.ok
    ? [`fixture compatibility failed: ${String((fixtureVerify.failures as unknown[]).join("; "))}`]
    : []),
];

const warnings = [
  ...(trainingRelease ? [] : ["training release verification was skipped because --metrics was not provided"]),
  ...(fixtureVerify ? [] : ["postprocess fixture verification was skipped because --fixture was not provided"]),
];

const summary = {
  ok: errors.length === 0,
  manifestPath: options.manifestPath,
  metricsPath: options.metricsPath ?? null,
  fixturePath: options.fixturePath ?? null,
  artifact,
  trainingRelease,
  fixtureVerify,
  contractChecks,
  errors,
  warnings,
  nextSteps:
    errors.length === 0
      ? [
          "Browser integration gate passed. You can continue with /ar-tryon manual UI verification.",
        ]
      : [
          "Fix the failing contract or runtime gate, then rerun verify-browser-integration.ts.",
        ],
};

console.log(JSON.stringify(summary, null, 2));
if (errors.length > 0) {
  process.exitCode = 1;
}
