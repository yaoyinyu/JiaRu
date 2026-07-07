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
  packageJsonPath: string;
  skipModelArtifact: boolean;
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    manifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    pickerPath: path.resolve("src/components/NailArtPicker.tsx"),
    clientWorkerPath: path.resolve("src/lib/nail-texture-recognition/client-worker.ts"),
    workerPath: path.resolve("src/workers/nail-texture-recognition.worker.ts"),
    runtimePath: path.resolve("src/lib/nail-texture-recognition/model-runtime.ts"),
    packageJsonPath: path.resolve("package.json"),
    skipModelArtifact: false,
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
    if (arg === "--package-json") {
      options.packageJsonPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--skip-model-artifact") {
      options.skipModelArtifact = true;
      continue;
    }
    throw new Error(
      "Usage: node --experimental-strip-types scripts/verify-browser-integration.ts [--manifest <manifest.json>] [--metrics <metrics.json>] [--fixture <fixture.json>] [--picker <NailArtPicker.tsx>] [--client-worker <client-worker.ts>] [--worker <worker.ts>] [--runtime <model-runtime.ts>] [--package-json <package.json>] [--skip-model-artifact]"
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
const artifact = options.skipModelArtifact
  ? null
  : await runJsonScript("scripts/verify-model-artifact.ts", [options.manifestPath]);
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
const packageJson = JSON.parse(await readFile(options.packageJsonPath, "utf8")) as {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};
const onnxRuntimeWebVersion =
  packageJson.dependencies?.["onnxruntime-web"] ?? packageJson.devDependencies?.["onnxruntime-web"] ?? null;

const contractChecks = [
  {
    name: "picker_uses_worker_recognition",
    ok: hasAll(pickerSource, [
      /recognizeNailTexturesInWorker/,
      /preferModel:\s*true/,
      /workerTimeoutMs:\s*NAIL_RECOGNITION_WORKER_TIMEOUT_MS/,
    ]),
  },
  {
    name: "picker_supports_end_to_end_cancellation",
    ok: hasAll(pickerSource, [
      /new AbortController\(\)/,
      /computeImageDetectedNailRegions\([\s\S]*controller\.signal[\s\S]*\)/,
      /detectionAbortRef\.current\?\.abort\(\)/,
      /onClick=\{cancelDetection\}/,
      /onClick=\{closePicker\}/,
    ]),
  },
  {
    name: "picker_caps_detection_input_and_remaps_candidates",
    ok: hasAll(pickerSource, [
      /MAX_DETECTION_DIM\s*=\s*800/,
      /calculateDetectionInputGeometry/,
      /ctx\.drawImage\(image, 0, 0, geometry\.width, geometry\.height\)/,
      /remapNailTextureCandidatesToOriginal/,
    ]),
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
        /workerElapsedMs:\s*result\.workerElapsedMs/,
        /warnings:\s*(?:result\.warnings|\[\s*\.\.\.result\.warnings\s*\])/,
      ]
    ),
  },
  {
    name: "client_worker_passes_manifest_and_prefer_model",
    ok: hasAll(clientWorkerSource, [/new Worker\(/, /preferModel:\s*options\.preferModel \?\? true/, /manifestUrl:\s*options\.manifestUrl/]),
  },
  {
    name: "client_worker_avoids_pixel_array_expansion",
    ok:
      /prepareWorkerImagePixels/.test(clientWorkerSource) &&
      !/Array\.from\(source\.data\)/.test(clientWorkerSource),
  },
  {
    name: "client_worker_terminates_on_abort",
    ok: hasAll(clientWorkerSource, [
      /signal\.addEventListener\("abort"/,
      /terminateWorkerAndRejectPending/,
      /worker\?\.terminate\(\)/,
    ]),
  },
  {
    name: "client_worker_times_out_to_fallback",
    ok: hasAll(clientWorkerSource, [
      /workerTimeoutMs/,
      /(?:workerTimeoutMs:\s*workerTimeoutMs|workerTimeoutMs,)/,
      /setTimeout\(/,
      /worker_timeout_used_main_thread/,
      /recognizeNailTextures\(source/,
      /workerInstance\?\.terminate\(\)/,
    ]),
  },
  {
    name: "worker_calls_recognition_and_posts_response",
    ok: hasAll(
      workerSource,
      [
        /recognizeNailTextures\(/,
        /self\.postMessage\(response\)/,
        /manifestUrl:\s*request\.manifestUrl/,
        /workerTimeoutMs:\s*request\.workerTimeoutMs/,
        /modelInfo:\s*result\.modelInfo/,
      ]
    ),
  },
  {
    name: "worker_releases_transferred_image_bitmap",
    ok: /request\.imageBitmap\.close\(\)/.test(workerSource),
  },
  {
    name: "runtime_loads_manifest_and_selects_execution_provider",
    ok: hasAll(runtimeSource, [/loadNailTextureModelManifest/, /createOrtSession/, /resolveOrtExecutionProviders/]),
  },
  {
    name: "package_declares_onnxruntime_web",
    ok: Boolean(onnxRuntimeWebVersion),
  },
];

const errors = [
  ...(artifact && !(artifact.ok as boolean) ? [String((artifact.errors as unknown[]).join("; "))] : []),
  ...contractChecks.filter((check) => !check.ok).map((check) => `browser contract check failed: ${check.name}`),
  ...(trainingRelease && !trainingRelease.ok
    ? [`training release gate failed: ${String((trainingRelease.errors as unknown[]).join("; "))}`]
    : []),
  ...(fixtureVerify && !fixtureVerify.ok
    ? [`fixture compatibility failed: ${String((fixtureVerify.failures as unknown[]).join("; "))}`]
    : []),
];

const warnings = [
  ...(options.skipModelArtifact ? ["model artifact verification was skipped by --skip-model-artifact"] : []),
  ...(trainingRelease ? [] : ["training release verification was skipped because --metrics was not provided"]),
  ...(fixtureVerify ? [] : ["postprocess fixture verification was skipped because --fixture was not provided"]),
];

const summary = {
  ok: errors.length === 0,
  manifestPath: options.manifestPath,
  packageJsonPath: options.packageJsonPath,
  onnxRuntimeWebVersion,
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
