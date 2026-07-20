import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const DEVICE_ACCEPTANCE_VERSION = "nail-texture-device-acceptance/v2";
export const DEVICE_FAMILIES = ["android", "android-tablet", "iphone", "ipad"] as const;
export type DeviceFamily = typeof DEVICE_FAMILIES[number];

type JsonRecord = Record<string, unknown>;

export interface DeviceEvidenceVerification {
  ok: boolean;
  errors: string[];
  performance: {
    sampleCount: number;
    p95Ms: number | null;
    maxElapsedMs: number | null;
    reportSha256: string;
    identity: {
      sessionId: string | null;
      deviceFamily: string | null;
      backend: string | null;
      modelVersion: string | null;
      inputSize: number | null;
    };
  };
  memory: {
    sampleCount: number;
    peakUsedJSHeapMiB: number | null;
    peakBrowserPrivateMiB: number | null;
    verificationSha256: string;
    rawReportPath: string | null;
    rawReportSha256: string | null;
    identity: {
      sessionId: string | null;
      deviceFamily: string | null;
      backend: string | null;
      modelVersion: string | null;
      inputSize: number | null;
    };
  };
}

export interface ApprovedDeviceReportVerification extends DeviceEvidenceVerification {
  found: boolean;
  report: JsonRecord | null;
}

function record(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function integer(value: unknown): number | null {
  const number = finite(value);
  return number !== null && Number.isInteger(number) ? number : null;
}

function string(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function samePath(left: string, right: string): boolean {
  const normalize = (value: string) => path.resolve(value).replaceAll("/", "\\").toLowerCase();
  return normalize(left) === normalize(right);
}

export async function sha256File(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function json(filePath: string): Promise<JsonRecord> {
  const parsed = JSON.parse(await readFile(filePath, "utf8")) as unknown;
  const document = record(parsed);
  if (!document) throw new Error(`Expected a JSON object: ${filePath}`);
  return document;
}

function percentile(values: number[], ratio: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * ratio) - 1);
  return Number(sorted[index]!.toFixed(2));
}

function average(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function maxConsecutiveIncrease(values: number[]): number {
  let current = 0;
  let maximum = 0;
  for (let index = 1; index < values.length; index += 1) {
    current = values[index]! > values[index - 1]! ? current + 1 : 0;
    maximum = Math.max(maximum, current);
  }
  return maximum;
}

function equalNumber(actual: unknown, expected: number | null): boolean {
  const value = finite(actual);
  if (expected === null) return value === null;
  return value !== null && Math.abs(value - expected) < 0.011;
}

function verifyPerformance(document: JsonRecord, errors: string[]) {
  const thresholds = record(document.thresholds) ?? {};
  const totals = record(document.totals) ?? {};
  const stats = record(document.stats) ?? {};
  const samples = Array.isArray(document.samples) ? document.samples : [];
  const maxElapsedMs = finite(thresholds.maxElapsedMs);
  const maxClientOverheadMs = thresholds.maxClientOverheadMs === null
    ? null
    : finite(thresholds.maxClientOverheadMs);
  const minSamples = integer(thresholds.minSamples);
  const elapsedValues: number[] = [];
  let malformedSamples = 0;
  let slowSamples = 0;
  let slowClientSamples = 0;
  const sessionIds = new Set<string>();
  const deviceFamilies = new Set<string>();
  const backends = new Set<string>();
  const modelVersions = new Set<string>();
  const inputSizes = new Set<number>();

  for (const value of samples) {
    const sample = record(value);
    const elapsedMs = sample ? finite(sample.elapsedMs) : null;
    const clientOverheadMs = sample && sample.clientOverheadMs !== null
      ? finite(sample.clientOverheadMs)
      : null;
    if (!sample || elapsedMs === null || elapsedMs < 0) {
      malformedSamples += 1;
      continue;
    }
    elapsedValues.push(elapsedMs);
    const sessionId = string(sample.sessionId);
    const deviceFamily = string(sample.deviceFamily);
    const backend = string(sample.backendName);
    const modelVersion = string(sample.modelVersion);
    const inputSize = integer(sample.inputSize);
    if (sessionId) sessionIds.add(sessionId);
    if (deviceFamily) deviceFamilies.add(deviceFamily);
    if (backend) backends.add(backend);
    if (modelVersion) modelVersions.add(modelVersion);
    if (inputSize !== null) inputSizes.add(inputSize);
    if (maxElapsedMs !== null && elapsedMs > maxElapsedMs) slowSamples += 1;
    if (maxClientOverheadMs !== null && clientOverheadMs !== null && clientOverheadMs > maxClientOverheadMs) {
      slowClientSamples += 1;
    }
  }

  if (document.profile !== "mobile") errors.push("performance profile must be mobile");
  if (document.ok !== true) errors.push("performance verification is not passing");
  if (minSamples === null || minSamples < 20) errors.push("performance minSamples must be at least 20");
  if (maxElapsedMs === null || maxElapsedMs <= 0) errors.push("performance maxElapsedMs must be positive");
  if (samples.length < 20) errors.push(`performance samples ${samples.length} are below 20`);
  if (integer(totals.samples) !== samples.length) errors.push("performance totals.samples does not match samples length");
  if (malformedSamples > 0) errors.push(`performance contains ${malformedSamples} malformed sample(s)`);
  if (slowSamples > 0) errors.push(`performance contains ${slowSamples} sample(s) above its elapsed budget`);
  if (slowClientSamples > 0) errors.push(`performance contains ${slowClientSamples} sample(s) above its client-overhead budget`);
  const p95Ms = percentile(elapsedValues, 0.95);
  if (!equalNumber(stats.p95Ms, p95Ms)) errors.push("performance stats.p95Ms does not match samples");
  if (integer(totals.slowSamples) !== slowSamples) errors.push("performance totals.slowSamples does not match samples");
  if (Array.isArray(document.errors) && document.errors.length > 0) errors.push("performance report contains errors");

  const identityDocument = record(document.identity) ?? {};
  const identitySets = {
    sessionIds: Array.isArray(identityDocument.sessionIds) ? identityDocument.sessionIds : [],
    deviceFamilies: Array.isArray(identityDocument.deviceFamilies) ? identityDocument.deviceFamilies : [],
    backends: Array.isArray(identityDocument.backends) ? identityDocument.backends : [],
    modelVersions: Array.isArray(identityDocument.modelVersions) ? identityDocument.modelVersions : [],
    inputSizes: Array.isArray(identityDocument.inputSizes) ? identityDocument.inputSizes : [],
  };
  const compareSet = (label: string, actual: Set<string | number>, reported: unknown[]) => {
    const normalized = [...actual].sort().map(String);
    const bound = reported.map(String).sort();
    if (JSON.stringify(normalized) !== JSON.stringify(bound)) errors.push(`performance identity.${label} does not match samples`);
    if (actual.size !== 1) errors.push(`performance requires exactly one ${label}`);
  };
  compareSet("sessionIds", sessionIds, identitySets.sessionIds);
  compareSet("deviceFamilies", deviceFamilies, identitySets.deviceFamilies);
  compareSet("backends", backends, identitySets.backends);
  compareSet("modelVersions", modelVersions, identitySets.modelVersions);
  compareSet("inputSizes", inputSizes, identitySets.inputSizes);
  const backend = [...backends][0] ?? null;
  if (backend === "fallback") errors.push("performance fallback backend is not eligible for device acceptance");

  return {
    sampleCount: samples.length,
    p95Ms,
    maxElapsedMs,
    identity: {
      sessionId: [...sessionIds][0] ?? null,
      deviceFamily: [...deviceFamilies][0] ?? null,
      backend,
      modelVersion: [...modelVersions][0] ?? null,
      inputSize: [...inputSizes][0] ?? null,
    },
  };
}

async function verifyMemory(document: JsonRecord, verificationPath: string, errors: string[]) {
  const thresholds = record(document.thresholds) ?? {};
  const totals = record(document.totals) ?? {};
  const stats = record(document.stats) ?? {};
  const minSamples = integer(thresholds.minSamples);
  const maxJsGrowthMiB = finite(thresholds.maxJsGrowthMiB);
  const maxPrivateGrowthMiB = finite(thresholds.maxPrivateGrowthMiB);
  const maxConsecutiveGrowth = integer(thresholds.maxConsecutiveGrowth);
  const rawPathValue = string(document.inputPath);
  const rawPath = rawPathValue ? path.resolve(rawPathValue) : null;

  if (document.ok !== true) errors.push("memory verification is not passing");
  if (minSamples === null || minSamples < 20) errors.push("memory minSamples must be at least 20");
  if (maxJsGrowthMiB === null || maxJsGrowthMiB < 0) errors.push("memory maxJsGrowthMiB must be non-negative");
  if (maxPrivateGrowthMiB === null || maxPrivateGrowthMiB < 0) errors.push("memory maxPrivateGrowthMiB must be non-negative");
  if (maxConsecutiveGrowth === null || maxConsecutiveGrowth < 0) errors.push("memory maxConsecutiveGrowth must be non-negative");
  if (!rawPath) errors.push("memory verification is missing inputPath");
  if (rawPath && samePath(rawPath, verificationPath)) errors.push("memory verification cannot use itself as raw input");

  let rawSha256: string | null = null;
  let sampleCount = 0;
  let peakUsedJSHeapMiB: number | null = null;
  let peakBrowserPrivateMiB: number | null = null;
  let identity = { sessionId: null, deviceFamily: null, backend: null, modelVersion: null, inputSize: null } as {
    sessionId: string | null;
    deviceFamily: string | null;
    backend: string | null;
    modelVersion: string | null;
    inputSize: number | null;
  };
  if (rawPath) {
    try {
      const raw = await json(rawPath);
      rawSha256 = await sha256File(rawPath);
      const samples = Array.isArray(raw.samples) ? raw.samples : [];
      identity = {
        sessionId: string(raw.sessionId),
        deviceFamily: string(raw.deviceFamily),
        backend: string(raw.backend),
        modelVersion: string(raw.modelVersion),
        inputSize: integer(raw.inputSize),
      };
      const usedJs: number[] = [];
      const privateBytes: number[] = [];
      let malformed = 0;
      for (const value of samples) {
        const sample = record(value);
        const js = sample ? finite(sample.usedJSHeapBytes) : null;
        const privateValue = sample ? finite(sample.browserPrivateBytes) : null;
        const workingSet = sample ? finite(sample.browserWorkingSetBytes) : null;
        const processCount = sample ? integer(sample.browserProcessCount) : null;
        if (!sample || js === null || js < 0 || privateValue === null || privateValue < 0 ||
          workingSet === null || workingSet < 0 || processCount === null || processCount < 0) {
          malformed += 1;
          continue;
        }
        usedJs.push(js);
        privateBytes.push(privateValue);
      }
      sampleCount = samples.length;
      if (raw.version !== "nail-texture-recognition-memory/v1") errors.push("unsupported raw memory report version");
      if (integer(raw.sampleCount) !== samples.length) errors.push("raw memory sampleCount does not match samples length");
      if (samples.length < 20) errors.push(`memory samples ${samples.length} are below 20`);
      if (malformed > 0) errors.push(`raw memory report contains ${malformed} malformed sample(s)`);

      const windowSize = Math.min(5, Math.floor(samples.length / 2));
      const firstJs = usedJs.slice(0, windowSize);
      const lastJs = usedJs.slice(-windowSize);
      const firstPrivate = privateBytes.slice(0, windowSize);
      const lastPrivate = privateBytes.slice(-windowSize);
      const mib = 1024 * 1024;
      const jsGrowthMiB = Number(((average(lastJs) - average(firstJs)) / mib).toFixed(2));
      const privateGrowthMiB = Number(((average(lastPrivate) - average(firstPrivate)) / mib).toFixed(2));
      const jsConsecutive = maxConsecutiveIncrease(usedJs);
      const privateConsecutive = maxConsecutiveIncrease(privateBytes);
      peakUsedJSHeapMiB = Number((Math.max(0, ...usedJs) / mib).toFixed(2));
      peakBrowserPrivateMiB = Number((Math.max(0, ...privateBytes) / mib).toFixed(2));

      if (maxJsGrowthMiB !== null && jsGrowthMiB > maxJsGrowthMiB) errors.push("raw memory JS growth exceeds threshold");
      if (maxPrivateGrowthMiB !== null && privateGrowthMiB > maxPrivateGrowthMiB) errors.push("raw memory private growth exceeds threshold");
      if (maxConsecutiveGrowth !== null && jsConsecutive > maxConsecutiveGrowth) errors.push("raw memory JS consecutive growth exceeds threshold");
      if (maxConsecutiveGrowth !== null && privateConsecutive > maxConsecutiveGrowth) errors.push("raw memory private consecutive growth exceeds threshold");
      if (!equalNumber(stats.peakUsedJSHeapMiB, peakUsedJSHeapMiB)) errors.push("memory peakUsedJSHeapMiB does not match raw samples");
      if (!equalNumber(stats.peakBrowserPrivateMiB, peakBrowserPrivateMiB)) errors.push("memory peakBrowserPrivateMiB does not match raw samples");
      if (!equalNumber(stats.jsLastWindowGrowthMiB, jsGrowthMiB)) errors.push("memory JS growth stat does not match raw samples");
      if (!equalNumber(stats.privateLastWindowGrowthMiB, privateGrowthMiB)) errors.push("memory private growth stat does not match raw samples");
      if (integer(stats.jsConsecutiveGrowth) !== jsConsecutive) errors.push("memory JS consecutive-growth stat does not match raw samples");
      if (integer(stats.privateConsecutiveGrowth) !== privateConsecutive) errors.push("memory private consecutive-growth stat does not match raw samples");
      if (integer(totals.samples) !== samples.length) errors.push("memory totals.samples does not match raw samples");
      const reportedIdentity = record(document.identity) ?? {};
      for (const key of ["sessionId", "deviceFamily", "backend", "modelVersion", "inputSize"] as const) {
        if (reportedIdentity[key] !== identity[key]) errors.push(`memory identity.${key} does not match raw report`);
        if (identity[key] === null) errors.push(`memory identity.${key} is required`);
      }
    } catch (error) {
      errors.push(`cannot verify raw memory input: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  if (Array.isArray(document.errors) && document.errors.length > 0) errors.push("memory verification contains errors");

  return { sampleCount, peakUsedJSHeapMiB, peakBrowserPrivateMiB, rawReportPath: rawPath, rawReportSha256: rawSha256, identity };
}

export async function verifyDeviceEvidence(performancePath: string, memoryPath: string): Promise<DeviceEvidenceVerification> {
  const resolvedPerformance = path.resolve(performancePath);
  const resolvedMemory = path.resolve(memoryPath);
  const errors: string[] = [];
  if (samePath(resolvedPerformance, resolvedMemory)) errors.push("performance and memory verification paths must differ");
  const performance = await json(resolvedPerformance);
  const memory = await json(resolvedMemory);
  const performanceSummary = verifyPerformance(performance, errors);
  const memorySummary = await verifyMemory(memory, resolvedMemory, errors);
  for (const key of ["sessionId", "deviceFamily", "backend", "modelVersion", "inputSize"] as const) {
    if (performanceSummary.identity[key] !== memorySummary.identity[key]) {
      errors.push(`performance and memory ${key} do not match`);
    }
  }
  return {
    ok: errors.length === 0,
    errors,
    performance: {
      ...performanceSummary,
      reportSha256: await sha256File(resolvedPerformance),
    },
    memory: {
      ...memorySummary,
      verificationSha256: await sha256File(resolvedMemory),
    },
  };
}

export async function verifyApprovedDeviceAcceptanceReport(
  reportPath: string,
  expectedDevice: string,
): Promise<ApprovedDeviceReportVerification> {
  const empty: ApprovedDeviceReportVerification = {
    found: false,
    ok: false,
    errors: [],
    report: null,
    performance: { sampleCount: 0, p95Ms: null, maxElapsedMs: null, reportSha256: "", identity: { sessionId: null, deviceFamily: null, backend: null, modelVersion: null, inputSize: null } },
    memory: { sampleCount: 0, peakUsedJSHeapMiB: null, peakBrowserPrivateMiB: null, verificationSha256: "", rawReportPath: null, rawReportSha256: null, identity: { sessionId: null, deviceFamily: null, backend: null, modelVersion: null, inputSize: null } },
  };
  let report: JsonRecord;
  try {
    report = await json(reportPath);
  } catch (error) {
    return { ...empty, errors: [`cannot read device report: ${error instanceof Error ? error.message : String(error)}`] };
  }
  const errors: string[] = [];
  const sourcePaths = record(report.sourcePaths) ?? {};
  const evidence = record(report.evidence) ?? {};
  const performanceEvidence = record(evidence.performance) ?? {};
  const memoryEvidence = record(evidence.memory) ?? {};
  const performancePath = string(sourcePaths.performance);
  const memoryPath = string(sourcePaths.memory);
  if (report.version !== DEVICE_ACCEPTANCE_VERSION) errors.push(`unsupported device report version ${String(report.version)}`);
  if (!DEVICE_FAMILIES.includes(expectedDevice as DeviceFamily)) errors.push(`unsupported expected device ${expectedDevice}`);
  if (report.deviceFamily !== expectedDevice) errors.push("device family does not match requested acceptance slot");
  if (report.ok !== true || report.decision !== "pass") errors.push("device acceptance report is not passing");
  if (!performancePath || !memoryPath) errors.push("device acceptance report is missing source paths");

  let replay = empty;
  if (performancePath && memoryPath) {
    try {
      replay = { ...empty, ...(await verifyDeviceEvidence(performancePath, memoryPath)) };
      errors.push(...replay.errors);
      if (replay.performance.identity.deviceFamily !== expectedDevice) errors.push("performance device family does not match requested acceptance slot");
      if (replay.memory.identity.deviceFamily !== expectedDevice) errors.push("memory device family does not match requested acceptance slot");
      if (report.backend !== replay.performance.identity.backend) errors.push("device report backend does not match replay");
      if (report.modelVersion !== replay.performance.identity.modelVersion) errors.push("device report model version does not match replay");
      if (report.inputSize !== replay.performance.identity.inputSize) errors.push("device report input size does not match replay");
      if (report.sessionId !== replay.performance.identity.sessionId) errors.push("device report session does not match replay");
      if (performanceEvidence.path !== path.resolve(performancePath)) errors.push("performance evidence path binding mismatch");
      if (performanceEvidence.sha256 !== replay.performance.reportSha256) errors.push("performance evidence SHA-256 mismatch");
      if (memoryEvidence.verificationPath !== path.resolve(memoryPath)) errors.push("memory verification path binding mismatch");
      if (memoryEvidence.verificationSha256 !== replay.memory.verificationSha256) errors.push("memory verification SHA-256 mismatch");
      if (memoryEvidence.rawReportPath !== replay.memory.rawReportPath) errors.push("raw memory path binding mismatch");
      if (memoryEvidence.rawReportSha256 !== replay.memory.rawReportSha256) errors.push("raw memory SHA-256 mismatch");
      const performanceSummary = record(report.performance) ?? {};
      const memorySummary = record(report.memory) ?? {};
      if (integer(performanceSummary.sampleCount) !== replay.performance.sampleCount || performanceSummary.ok !== true) {
        errors.push("device performance summary does not match replay");
      }
      if (integer(memorySummary.sampleCount) !== replay.memory.sampleCount || memorySummary.ok !== true) {
        errors.push("device memory summary does not match replay");
      }
    } catch (error) {
      errors.push(`cannot replay device evidence: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return { ...replay, found: true, ok: errors.length === 0, errors, report };
}
