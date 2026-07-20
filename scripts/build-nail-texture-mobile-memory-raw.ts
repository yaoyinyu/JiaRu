import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseCsv } from "./lib/simple-csv.ts";
import { sha256File } from "./lib/nail-texture-device-acceptance.ts";

const HEADER = [
  "iteration",
  "usedJSHeapMiB",
  "browserPrivateMiB",
  "browserWorkingSetMiB",
  "browserProcessCount",
];
const DEVICE_FAMILIES = new Set(["android", "android-tablet", "iphone", "ipad"]);

function required(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`Missing required argument ${name}`);
  return value;
}

function number(value: string, field: string, row: number, allowZero = true): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || (allowZero ? parsed < 0 : parsed <= 0)) {
    throw new Error(`CSV row ${row} ${field} must be ${allowZero ? "non-negative" : "positive"}`);
  }
  return parsed;
}

const csvPath = path.resolve(required("--csv"));
const sessionPath = path.resolve(required("--session"));
const outputPath = path.resolve(required("--output"));
if ([csvPath, sessionPath].some((input) => input.toLowerCase() === outputPath.toLowerCase())) {
  throw new Error("--output must not overwrite an input file");
}
const session = JSON.parse(await readFile(sessionPath, "utf8")) as Record<string, unknown>;
if (session.version !== "nail-texture-device-session/v1") throw new Error("unsupported device session version");
if (session.eligibleForPerformanceVerification !== true) throw new Error("device session is not eligible for performance verification");
const sessionId = typeof session.sessionId === "string" ? session.sessionId : "";
const deviceFamily = typeof session.deviceFamily === "string" ? session.deviceFamily : "";
const modelVersion = typeof session.modelVersion === "string" ? session.modelVersion : "";
const backend = typeof session.backend === "string" ? session.backend : "";
const inputSize = Number(session.inputSize);
if (!sessionId) throw new Error("device session is missing sessionId");
if (!DEVICE_FAMILIES.has(deviceFamily)) throw new Error("device session has unsupported deviceFamily");
if (!modelVersion || (backend !== "webgpu" && backend !== "wasm")) throw new Error("device session has invalid model identity");
if (!Number.isInteger(inputSize) || inputSize <= 0) throw new Error("device session has invalid inputSize");

const rows = parseCsv(await readFile(csvPath, "utf8"), HEADER);
if (rows.length < 20) throw new Error(`memory sample count ${rows.length} is below 20`);
const mib = 1024 * 1024;
const samples = rows.map((row, index) => {
  const csvRow = index + 2;
  const iteration = number(row.iteration!, "iteration", csvRow, false);
  if (!Number.isInteger(iteration) || iteration !== index + 1) {
    throw new Error(`CSV row ${csvRow} iteration must equal ${index + 1}`);
  }
  return {
    iteration,
    usedJSHeapBytes: Math.round(number(row.usedJSHeapMiB!, "usedJSHeapMiB", csvRow) * mib),
    browserPrivateBytes: Math.round(number(row.browserPrivateMiB!, "browserPrivateMiB", csvRow, false) * mib),
    browserWorkingSetBytes: Math.round(number(row.browserWorkingSetMiB!, "browserWorkingSetMiB", csvRow, false) * mib),
    browserProcessCount: number(row.browserProcessCount!, "browserProcessCount", csvRow, false),
  };
});
if (samples.some((sample) => !Number.isInteger(sample.browserProcessCount))) {
  throw new Error("browserProcessCount values must be integers");
}

const report = {
  version: "nail-texture-recognition-memory/v1",
  profile: deviceFamily,
  generatedAt: new Date().toISOString(),
  sessionId,
  deviceFamily,
  modelVersion,
  backend,
  inputSize,
  sampleCount: samples.length,
  sourceEvidence: {
    deviceSessionPath: sessionPath,
    deviceSessionSha256: await sha256File(sessionPath),
    profilerCsvPath: csvPath,
    profilerCsvSha256: await sha256File(csvPath),
    note: "browserPrivateMiB and browserWorkingSetMiB must come from Android Profiler/system sampling or iOS Instruments, not from browser JavaScript estimates.",
  },
  samples,
};
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
