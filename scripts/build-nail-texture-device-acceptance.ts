import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const DEVICE_FAMILIES = new Set(["android", "android-tablet", "iphone", "ipad"]);

function arg(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}
function required(name: string): string {
  const value = arg(name);
  if (!value) throw new Error(`Missing required argument ${name}`);
  return value;
}
async function json(filePath: string): Promise<Record<string, unknown>> {
  const value = JSON.parse(await readFile(filePath, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`Expected JSON object: ${filePath}`);
  return value;
}

const deviceFamily = required("--device-family");
if (!DEVICE_FAMILIES.has(deviceFamily)) throw new Error(`Unsupported device family: ${deviceFamily}`);
const deviceName = required("--device-name");
const operatingSystem = required("--os");
const browser = required("--browser");
const backend = required("--backend");
const performancePath = path.resolve(required("--performance"));
const memoryPath = path.resolve(required("--memory"));
const outputPath = path.resolve(required("--output"));
const performance = await json(performancePath);
const memory = await json(memoryPath);
const performanceTotals = performance.totals as { samples?: number } | undefined;
const memoryTotals = memory.totals as { samples?: number } | undefined;
const performanceSamples = Number(performanceTotals?.samples ?? 0);
const memorySamples = Number(memoryTotals?.samples ?? memory.sampleCount ?? 0);
const errors: string[] = [];
if (performance.ok !== true) errors.push("performance verification is not passing");
if (memory.ok !== true) errors.push("memory verification is not passing");
if (performanceSamples < 20) errors.push(`performance samples ${performanceSamples} are below 20`);
if (memorySamples < 20) errors.push(`memory samples ${memorySamples} are below 20`);
const report = {
  version: "nail-texture-device-acceptance/v1",
  deviceFamily,
  deviceName,
  operatingSystem,
  browser,
  backend,
  ok: errors.length === 0,
  decision: errors.length === 0 ? "pass" : "hold",
  performance: { ok: performance.ok === true && performanceSamples >= 20, sampleCount: performanceSamples, thresholds: performance.thresholds ?? null, stats: performance.stats ?? null },
  memory: { ok: memory.ok === true && memorySamples >= 20, sampleCount: memorySamples, thresholds: memory.thresholds ?? null, stats: memory.stats ?? null },
  sourcePaths: { performance: performancePath, memory: memoryPath },
  errors,
};
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exitCode = 1;
