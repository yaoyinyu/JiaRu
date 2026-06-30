import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface CliOptions {
  manifestPath: string;
  dumpPath?: string;
  fixtureOutPath?: string;
  imagePath?: string;
  annotationPath?: string;
  debugOutputDir?: string;
  debugPrefix?: string;
}

function parseArgs(argv: string[]): CliOptions {
  let manifestPath = "public/models/nail-texture-seg/manifest.json";
  let dumpPath: string | undefined;
  let fixtureOutPath: string | undefined;
  let imagePath: string | undefined;
  let annotationPath: string | undefined;
  let debugOutputDir: string | undefined;
  let debugPrefix: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--manifest") {
      manifestPath = argv[++index];
      continue;
    }
    if (arg === "--dump") {
      dumpPath = argv[++index];
      continue;
    }
    if (arg === "--fixture-out") {
      fixtureOutPath = argv[++index];
      continue;
    }
    if (arg === "--image") {
      imagePath = argv[++index];
      continue;
    }
    if (arg === "--annotation") {
      annotationPath = argv[++index];
      continue;
    }
    if (arg === "--debug-output-dir") {
      debugOutputDir = argv[++index];
      continue;
    }
    if (arg === "--debug-prefix") {
      debugPrefix = argv[++index];
      continue;
    }
    throw new Error(
      "Usage: node --experimental-strip-types scripts/verify-real-model-readiness.ts [--manifest <manifest.json>] [--dump <nail-model-output-dump.json>] [--fixture-out <fixture.json>] [--image <image>] [--annotation <green-annotation-image>] [--debug-output-dir <dir>] [--debug-prefix <name>]"
    );
  }

  return {
    manifestPath: path.resolve(manifestPath),
    dumpPath: dumpPath ? path.resolve(dumpPath) : undefined,
    fixtureOutPath: fixtureOutPath ? path.resolve(fixtureOutPath) : undefined,
    imagePath: imagePath ? path.resolve(imagePath) : undefined,
    annotationPath: annotationPath ? path.resolve(annotationPath) : undefined,
    debugOutputDir: debugOutputDir ? path.resolve(debugOutputDir) : undefined,
    debugPrefix,
  };
}

async function runJsonScript(scriptPath: string, args: string[]) {
  try {
    const { stdout } = await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", scriptPath, ...args],
      {
        cwd: path.resolve("."),
      }
    );
    return {
      ok: true,
      result: JSON.parse(stdout) as Record<string, unknown>,
    };
  } catch (error) {
    const execError = error as {
      stdout?: string;
      stderr?: string;
      message?: string;
    };
    if (execError.stdout) {
      return {
        ok: false,
        result: JSON.parse(execError.stdout) as Record<string, unknown>,
      };
    }
    throw error;
  }
}

const options = parseArgs(process.argv.slice(2));
const artifactRun = await runJsonScript("scripts/verify-model-artifact.ts", [
  options.manifestPath,
]);
const artifact = artifactRun.result;

let fixtureBuild: Record<string, unknown> | null = null;
let fixtureVerify: Record<string, unknown> | null = null;
let fixturePath: string | null = null;
let imageVerify: Record<string, unknown> | null = null;

if (options.dumpPath) {
  fixturePath =
    options.fixtureOutPath ??
    options.dumpPath.replace(/-dump\.json$/i, "-fixture.json");
  fixtureBuild = (await runJsonScript("scripts/build-model-output-fixture.ts", [
    options.dumpPath,
    fixturePath,
  ])).result;
  fixtureVerify = (await runJsonScript("scripts/verify-model-output-fixture.ts", [
    fixturePath,
  ])).result;
}

if (options.imagePath && Boolean(artifact.ok)) {
  const args = [options.imagePath];
  if (options.annotationPath) {
    args.push(options.annotationPath);
  }
  if (options.debugOutputDir) {
    args.push("--output-dir", options.debugOutputDir);
  }
  if (options.debugPrefix) {
    args.push("--prefix", options.debugPrefix);
  }
  imageVerify = (await runJsonScript("scripts/verify-nail-detection.ts", args)).result;
}

const ok =
  Boolean(artifact.ok) &&
  (fixtureBuild === null || fixtureVerify === null || Boolean(fixtureVerify.ok)) &&
  (imageVerify === null || (typeof imageVerify.count === "number" && imageVerify.count >= 4));

console.log(
  JSON.stringify(
    {
      ok,
      manifestPath: options.manifestPath,
      dumpPath: options.dumpPath ?? null,
      fixturePath,
      artifact,
      fixtureBuild,
      fixtureVerify,
      imageVerify,
      nextSteps:
        !Boolean(artifact.ok)
          ? [
              "Fix the model artifact first. After you obtain the ONNX file, rerun this readiness script.",
            ]
          : options.imagePath
            ? [
                "If image verification looks good, continue with /ar-tryon UI checks.",
              ]
            : options.dumpPath
              ? [
                  "Artifact and fixture verification are complete. You can now rerun with --image for single-image detection validation.",
                ]
              : [
                  "Artifact check is complete. After you obtain a real model output dump, rerun with --dump to validate postprocess compatibility.",
                ],
    },
    null,
    2
  )
);

if (!ok) {
  process.exitCode = 1;
}
