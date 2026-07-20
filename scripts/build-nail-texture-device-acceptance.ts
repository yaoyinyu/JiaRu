import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  DEVICE_ACCEPTANCE_VERSION,
  DEVICE_FAMILIES,
  verifyDeviceEvidence,
} from "./lib/nail-texture-device-acceptance.ts";

function arg(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}
function required(name: string): string {
  const value = arg(name);
  if (!value) throw new Error(`Missing required argument ${name}`);
  return value;
}
const deviceFamily = required("--device-family");
if (!DEVICE_FAMILIES.includes(deviceFamily as typeof DEVICE_FAMILIES[number])) throw new Error(`Unsupported device family: ${deviceFamily}`);
const deviceName = required("--device-name");
const operatingSystem = required("--os");
const browser = required("--browser");
const backend = required("--backend");
const performancePath = path.resolve(required("--performance"));
const memoryPath = path.resolve(required("--memory"));
const outputPath = path.resolve(required("--output"));
if ([performancePath, memoryPath].some((input) => input.toLowerCase() === outputPath.toLowerCase())) {
  throw new Error("--output must not overwrite an input evidence file");
}
const verification = await verifyDeviceEvidence(performancePath, memoryPath);
const errors = verification.errors;
if (verification.performance.identity.deviceFamily !== deviceFamily) {
  errors.push("device family does not match bound performance and memory evidence");
}
if (verification.performance.identity.backend !== backend) {
  errors.push("backend does not match bound performance and memory evidence");
}
const report = {
  version: DEVICE_ACCEPTANCE_VERSION,
  generatedAt: new Date().toISOString(),
  deviceFamily,
  deviceName,
  operatingSystem,
  browser,
  backend,
  sessionId: verification.performance.identity.sessionId,
  modelVersion: verification.performance.identity.modelVersion,
  inputSize: verification.performance.identity.inputSize,
  ok: errors.length === 0,
  decision: errors.length === 0 ? "pass" : "hold",
  performance: {
    ok: verification.ok,
    sampleCount: verification.performance.sampleCount,
    p95Ms: verification.performance.p95Ms,
    maxElapsedMs: verification.performance.maxElapsedMs,
  },
  memory: {
    ok: verification.ok,
    sampleCount: verification.memory.sampleCount,
    peakUsedJSHeapMiB: verification.memory.peakUsedJSHeapMiB,
    peakBrowserPrivateMiB: verification.memory.peakBrowserPrivateMiB,
  },
  sourcePaths: { performance: performancePath, memory: memoryPath },
  evidence: {
    performance: { path: performancePath, sha256: verification.performance.reportSha256 },
    memory: {
      verificationPath: memoryPath,
      verificationSha256: verification.memory.verificationSha256,
      rawReportPath: verification.memory.rawReportPath,
      rawReportSha256: verification.memory.rawReportSha256,
    },
  },
  errors,
};
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exitCode = 1;
