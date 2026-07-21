import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { parseCsv } from "./simple-csv.ts";

export const RELEASE_PRODUCT_QUALITY_VERSION = "nail-texture-release-product-quality/v1";
export const INSTANCE_REVIEW_HEADER = [
  "fileName",
  "sourceGroup",
  "imageSha256",
  "instanceIndex",
  "decision",
  "contaminated",
  "roughRectangle",
  "predictedPixels",
  "outsideGtPixels",
  "gtPixels",
  "missedGtPixels",
] as const;
export const SCENARIO_REGRESSION_HEADER = [
  "dimension",
  "name",
  "sampleCount",
  "baselineBoxMap50",
  "candidateBoxMap50",
  "baselineMaskMap50",
  "candidateMaskMap50",
] as const;
export const REQUIRED_SCENARIO_DIMENSIONS = [
  "skin-tone",
  "nail-color",
  "reflectivity",
  "occlusion",
  "orientation",
  "nail-count",
  "background",
  "device-backend",
] as const;

const DECISIONS = ["directly_usable", "needs_fix", "unusable"] as const;
const DIRECTLY_USABLE_MINIMUM = 0.85;
const CONTAMINATION_MAXIMUM_EXCLUSIVE = 0.10;
const ROUGH_RECTANGLE_MAXIMUM = 0.15;
const MISSING_RATE_MAXIMUM = 0.10;
const MINIMUM_ALLOWED_DELTA = -0.02;
const SHA256 = /^[a-f0-9]{64}$/i;
const CANONICAL_NUMBER_TOKEN = Symbol("canonicalNumberToken");

type JsonRecord = Record<string, unknown>;
type CanonicalNumber = { [CANONICAL_NUMBER_TOKEN]: string };
type Decision = typeof DECISIONS[number];
type ScenarioDimension = typeof REQUIRED_SCENARIO_DIMENSIONS[number];

interface SnapshotItem {
  fileName: string;
  sourceGroup: string;
  imageSha256: string;
  maskCount: number;
}

interface InstanceRecord extends SnapshotItem {
  instanceIndex: number;
  decision: Decision;
  contaminated: boolean;
  roughRectangle: boolean;
  predictedPixels: number;
  outsideGtPixels: number;
  gtPixels: number;
  missedGtPixels: number;
}

export interface ScenarioGroup {
  dimension: ScenarioDimension;
  name: string;
  sampleCount: number;
  baselineBoxMap50: number;
  candidateBoxMap50: number;
  boxMap50Delta: number;
  baselineMaskMap50: number;
  candidateMaskMap50: number;
  maskMap50Delta: number;
  ok: boolean;
}

export interface ReleaseProductQualityReport extends JsonRecord {
  version: typeof RELEASE_PRODUCT_QUALITY_VERSION;
  generatedAt: string;
  ok: boolean;
  decision: "pass" | "hold";
  reviewedByUser: boolean;
  reviewer: string;
  trainingUse: "prohibited";
  snapshot: {
    path: string;
    sha256: string | null;
    itemsSha256: string | null;
    imageCount: number;
    maskCount: number;
  };
  rawEvidence: {
    instances: { path: string; sha256: string | null; rowCount: number };
    scenarios: { path: string; sha256: string | null; rowCount: number };
  };
  sampleImages: number;
  sampleInstances: number;
  directlyUsableRate: number | null;
  contaminationInstanceRate: number | null;
  roughRectangleRate: number | null;
  pixelLeakageRate: number | null;
  missingRate: number | null;
  frozenMaximumMissingRate: typeof MISSING_RATE_MAXIMUM;
  minimumAllowedDelta: typeof MINIMUM_ALLOWED_DELTA;
  scenarioGroups: ScenarioGroup[];
  errors: string[];
}

export interface ApprovedReleaseProductQualityVerification {
  found: boolean;
  ok: boolean;
  errors: string[];
  report: JsonRecord | null;
  replay: ReleaseProductQualityReport | null;
}

function record(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseNonNegativeInteger(value: string): number | null {
  if (!/^(0|[1-9]\d*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function parsePositiveInteger(value: string): number | null {
  const parsed = parseNonNegativeInteger(value);
  return parsed !== null && parsed > 0 ? parsed : null;
}

function parseRate(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : null;
}

function parseBoolean(value: string): boolean | null {
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

function rounded(value: number): number {
  return Number(value.toFixed(12));
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    const numberToken = (value as Partial<CanonicalNumber>)[CANONICAL_NUMBER_TOKEN];
    if (typeof numberToken === "string") return numberToken;
    const entries = Object.entries(value as JsonRecord).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0);
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function canonicalSha256(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function pythonJsonNumber(source: string): string {
  if (!/[.eE]/.test(source)) return BigInt(source).toString();
  const value = Number(source);
  if (Object.is(value, -0)) return "-0.0";
  let rendered = String(value).toLowerCase();
  if (!rendered.includes("e")) return rendered.includes(".") ? rendered : `${rendered}.0`;
  const [mantissa, exponentSource] = rendered.split("e") as [string, string];
  const exponent = Number(exponentSource);
  const sign = exponent >= 0 ? "+" : "-";
  return `${mantissa}e${sign}${Math.abs(exponent).toString().padStart(2, "0")}`;
}

function parseWithNumberTokens(text: string): unknown {
  return JSON.parse(text, (_key, value, context?: { source?: string }) => {
    if (typeof value === "number" && context?.source) {
      return { [CANONICAL_NUMBER_TOKEN]: pythonJsonNumber(context.source) } satisfies CanonicalNumber;
    }
    return value;
  }) as unknown;
}

function ratio(numerator: number, denominator: number): number | null {
  return denominator > 0 ? rounded(numerator / denominator) : null;
}

function normalizePath(value: string): string {
  return path.resolve(value).replaceAll("/", "\\").toLowerCase();
}

export function sameEvidencePath(left: string, right: string): boolean {
  return normalizePath(left) === normalizePath(right);
}

export async function sha256EvidenceFile(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function readJsonObject(filePath: string): Promise<JsonRecord> {
  const parsed = JSON.parse(await readFile(filePath, "utf8")) as unknown;
  const document = record(parsed);
  if (!document) throw new Error(`expected a JSON object: ${filePath}`);
  return document;
}

function validateSnapshot(document: JsonRecord, canonicalItems: unknown, errors: string[]): {
  items: SnapshotItem[];
  itemsSha256: string | null;
  imageCount: number;
  maskCount: number;
} {
  const itemsValue = Array.isArray(document.items) ? document.items : [];
  const counts = record(document.counts) ?? {};
  const items: SnapshotItem[] = [];
  const names = new Set<string>();
  const imageHashes = new Set<string>();
  const representativeGate = record(document.representativeReleaseGate) ?? {};
  if (document.decision !== "frozen_reviewed_candidate_not_release_ready") {
    errors.push("snapshot decision must be frozen_reviewed_candidate_not_release_ready");
  }
  if (document.trainingUse !== "prohibited") errors.push("snapshot trainingUse must be prohibited");
  if (itemsValue.length === 0) errors.push("snapshot items must be a non-empty array");
  const itemsSha256 = nonEmptyString(document.itemsSha256);
  if (!itemsSha256 || !SHA256.test(itemsSha256)) errors.push("snapshot itemsSha256 must be a SHA-256 digest");

  for (const [index, value] of itemsValue.entries()) {
    const item = record(value);
    const fileName = item ? nonEmptyString(item.fileName) : null;
    const sourceGroup = item ? nonEmptyString(item.sourceGroup) : null;
    const imageSha256 = item ? nonEmptyString(item.imageSha256) : null;
    const maskCount = item && typeof item.maskCount === "number" && Number.isSafeInteger(item.maskCount) && item.maskCount > 0
      ? item.maskCount
      : null;
    if (!item || !fileName || !sourceGroup || !imageSha256 || !SHA256.test(imageSha256) || maskCount === null) {
      errors.push(`snapshot item ${index + 1} has invalid identity or maskCount`);
      continue;
    }
    if (item.trainingUse !== "prohibited") errors.push(`snapshot item ${index + 1} trainingUse must be prohibited`);
    if (names.has(fileName)) {
      errors.push(`snapshot contains duplicate fileName ${fileName}`);
      continue;
    }
    const normalizedImageSha256 = imageSha256.toLowerCase();
    if (imageHashes.has(normalizedImageSha256)) {
      errors.push(`snapshot contains duplicate imageSha256 ${normalizedImageSha256}`);
      continue;
    }
    names.add(fileName);
    imageHashes.add(normalizedImageSha256);
    items.push({ fileName, sourceGroup, imageSha256: normalizedImageSha256, maskCount });
  }
  const imageCount = items.length;
  const maskCount = items.reduce((sum, item) => sum + item.maskCount, 0);
  if (counts.images !== itemsValue.length || counts.images !== imageCount) {
    errors.push("snapshot counts.images does not match valid items");
  }
  if (counts.masks !== maskCount) errors.push("snapshot counts.masks does not match item maskCount total");
  if (itemsSha256 && SHA256.test(itemsSha256) && itemsSha256.toLowerCase() !== canonicalSha256(canonicalItems)) {
    errors.push("snapshot itemsSha256 does not match canonical items");
  }
  if (imageCount < 100) errors.push(`snapshot image count ${imageCount} is below representative minimum 100`);
  if (representativeGate.required !== 100 || representativeGate.actual !== imageCount || representativeGate.ok !== true) {
    errors.push("snapshot representativeReleaseGate must declare required=100, actual=imageCount and ok=true");
  }
  return { items, itemsSha256: itemsSha256?.toLowerCase() ?? null, imageCount, maskCount };
}

function parseInstanceRows(
  text: string,
  snapshotItems: SnapshotItem[],
  errors: string[],
): { records: InstanceRecord[]; rowCount: number } {
  let rows: Array<Record<string, string>>;
  try {
    rows = parseCsv(text, [...INSTANCE_REVIEW_HEADER]);
  } catch (error) {
    errors.push(`cannot parse instance CSV: ${error instanceof Error ? error.message : String(error)}`);
    return { records: [], rowCount: 0 };
  }
  const snapshotByName = new Map(snapshotItems.map((item) => [item.fileName, item]));
  const seen = new Set<string>();
  const records: InstanceRecord[] = [];
  for (const [index, row] of rows.entries()) {
    const label = `instance CSV row ${index + 2}`;
    const fileName = row.fileName ?? "";
    const expected = snapshotByName.get(fileName);
    const instanceIndex = parsePositiveInteger(row.instanceIndex ?? "");
    const decision = DECISIONS.includes((row.decision ?? "") as Decision) ? row.decision as Decision : null;
    const contaminated = parseBoolean(row.contaminated ?? "");
    const roughRectangle = parseBoolean(row.roughRectangle ?? "");
    const predictedPixels = parseNonNegativeInteger(row.predictedPixels ?? "");
    const outsideGtPixels = parseNonNegativeInteger(row.outsideGtPixels ?? "");
    const gtPixels = parseNonNegativeInteger(row.gtPixels ?? "");
    const missedGtPixels = parseNonNegativeInteger(row.missedGtPixels ?? "");
    if (!expected) errors.push(`${label}: fileName is not present in snapshot: ${fileName || "<empty>"}`);
    if (!row.sourceGroup) errors.push(`${label}: sourceGroup is required`);
    if (!SHA256.test(row.imageSha256 ?? "")) errors.push(`${label}: imageSha256 must be a SHA-256 digest`);
    if (expected && row.sourceGroup !== expected.sourceGroup) errors.push(`${label}: sourceGroup does not match snapshot`);
    if (expected && (row.imageSha256 ?? "").toLowerCase() !== expected.imageSha256) errors.push(`${label}: imageSha256 does not match snapshot`);
    if (instanceIndex === null) errors.push(`${label}: instanceIndex must be a positive integer`);
    if (expected && instanceIndex !== null && instanceIndex > expected.maskCount) errors.push(`${label}: instanceIndex exceeds snapshot maskCount`);
    if (!decision) errors.push(`${label}: invalid decision`);
    if (contaminated === null) errors.push(`${label}: contaminated must be true or false`);
    if (roughRectangle === null) errors.push(`${label}: roughRectangle must be true or false`);
    if (predictedPixels === null) errors.push(`${label}: predictedPixels must be a non-negative integer`);
    if (outsideGtPixels === null) errors.push(`${label}: outsideGtPixels must be a non-negative integer`);
    if (gtPixels === null) errors.push(`${label}: gtPixels must be a non-negative integer`);
    if (missedGtPixels === null) errors.push(`${label}: missedGtPixels must be a non-negative integer`);
    if (predictedPixels !== null && outsideGtPixels !== null && outsideGtPixels > predictedPixels) {
      errors.push(`${label}: outsideGtPixels must not exceed predictedPixels`);
    }
    if (gtPixels !== null && missedGtPixels !== null && missedGtPixels > gtPixels) {
      errors.push(`${label}: missedGtPixels must not exceed gtPixels`);
    }
    const key = expected && instanceIndex !== null ? `${fileName}\u0000${instanceIndex}` : null;
    if (key && seen.has(key)) errors.push(`${label}: duplicate fileName and instanceIndex`);
    const valid = expected && instanceIndex !== null && instanceIndex <= expected.maskCount && decision &&
      contaminated !== null && roughRectangle !== null && predictedPixels !== null && outsideGtPixels !== null &&
      gtPixels !== null && missedGtPixels !== null && outsideGtPixels <= predictedPixels && missedGtPixels <= gtPixels &&
      row.sourceGroup === expected.sourceGroup && (row.imageSha256 ?? "").toLowerCase() === expected.imageSha256 &&
      key !== null && !seen.has(key);
    if (key) seen.add(key);
    if (valid) {
      records.push({ ...expected, instanceIndex, decision, contaminated, roughRectangle, predictedPixels, outsideGtPixels, gtPixels, missedGtPixels });
    }
  }
  for (const item of snapshotItems) {
    for (let instanceIndex = 1; instanceIndex <= item.maskCount; instanceIndex += 1) {
      if (!seen.has(`${item.fileName}\u0000${instanceIndex}`)) {
        errors.push(`instance CSV is missing ${item.fileName} instanceIndex ${instanceIndex}`);
      }
    }
  }
  return { records, rowCount: rows.length };
}

function parseScenarioRows(text: string, maximumSampleCount: number, errors: string[]): { groups: ScenarioGroup[]; rowCount: number } {
  let rows: Array<Record<string, string>>;
  try {
    rows = parseCsv(text, [...SCENARIO_REGRESSION_HEADER]);
  } catch (error) {
    errors.push(`cannot parse scenario CSV: ${error instanceof Error ? error.message : String(error)}`);
    return { groups: [], rowCount: 0 };
  }
  const groups: ScenarioGroup[] = [];
  const seen = new Set<string>();
  for (const [index, row] of rows.entries()) {
    const label = `scenario CSV row ${index + 2}`;
    const dimension = REQUIRED_SCENARIO_DIMENSIONS.includes((row.dimension ?? "") as ScenarioDimension)
      ? row.dimension as ScenarioDimension
      : null;
    const name = row.name?.trim() ?? "";
    const sampleCount = parsePositiveInteger(row.sampleCount ?? "");
    const baselineBoxMap50 = parseRate(row.baselineBoxMap50 ?? "");
    const candidateBoxMap50 = parseRate(row.candidateBoxMap50 ?? "");
    const baselineMaskMap50 = parseRate(row.baselineMaskMap50 ?? "");
    const candidateMaskMap50 = parseRate(row.candidateMaskMap50 ?? "");
    if (!dimension) errors.push(`${label}: invalid dimension`);
    if (!name) errors.push(`${label}: name is required`);
    if (sampleCount === null) errors.push(`${label}: sampleCount must be a positive integer`);
    if (sampleCount !== null && sampleCount > maximumSampleCount) errors.push(`${label}: sampleCount exceeds snapshot image count`);
    for (const [field, value] of [
      ["baselineBoxMap50", baselineBoxMap50],
      ["candidateBoxMap50", candidateBoxMap50],
      ["baselineMaskMap50", baselineMaskMap50],
      ["candidateMaskMap50", candidateMaskMap50],
    ] as const) if (value === null) errors.push(`${label}: ${field} must be in [0,1]`);
    const key = dimension && name ? `${dimension}\u0000${name}` : null;
    if (key && seen.has(key)) errors.push(`${label}: duplicate dimension and name`);
    if (key) seen.add(key);
    if (dimension && name && sampleCount !== null && baselineBoxMap50 !== null && candidateBoxMap50 !== null &&
      baselineMaskMap50 !== null && candidateMaskMap50 !== null && key && !groups.some((group) => `${group.dimension}\u0000${group.name}` === key)) {
      const boxMap50Delta = rounded(candidateBoxMap50 - baselineBoxMap50);
      const maskMap50Delta = rounded(candidateMaskMap50 - baselineMaskMap50);
      const ok = boxMap50Delta >= MINIMUM_ALLOWED_DELTA && maskMap50Delta >= MINIMUM_ALLOWED_DELTA;
      if (!ok) errors.push(`${label}: box/mask mAP50 delta is below ${MINIMUM_ALLOWED_DELTA}`);
      groups.push({ dimension, name, sampleCount, baselineBoxMap50, candidateBoxMap50, boxMap50Delta, baselineMaskMap50, candidateMaskMap50, maskMap50Delta, ok });
    }
  }
  const present = new Set(groups.map((group) => group.dimension));
  for (const dimension of REQUIRED_SCENARIO_DIMENSIONS) {
    if (!present.has(dimension)) errors.push(`scenario CSV is missing required dimension ${dimension}`);
  }
  return { groups, rowCount: rows.length };
}

async function readEvidenceText(filePath: string, label: string, errors: string[]): Promise<{ text: string; sha256: string | null }> {
  try {
    const bytes = await readFile(filePath);
    return { text: bytes.toString("utf8"), sha256: createHash("sha256").update(bytes).digest("hex") };
  } catch (error) {
    errors.push(`cannot read ${label}: ${error instanceof Error ? error.message : String(error)}`);
    return { text: "", sha256: null };
  }
}

export async function buildReleaseProductQualityEvidence(input: {
  snapshotPath: string;
  instancesCsvPath: string;
  scenariosCsvPath: string;
  reviewer: string;
}): Promise<ReleaseProductQualityReport> {
  const snapshotPath = path.resolve(input.snapshotPath);
  const instancesCsvPath = path.resolve(input.instancesCsvPath);
  const scenariosCsvPath = path.resolve(input.scenariosCsvPath);
  const reviewer = input.reviewer.trim();
  const errors: string[] = [];
  if (!reviewer) errors.push("reviewer is required");
  const snapshotEvidence = await readEvidenceText(snapshotPath, "snapshot", errors);
  const instanceEvidence = await readEvidenceText(instancesCsvPath, "instance CSV", errors);
  const scenarioEvidence = await readEvidenceText(scenariosCsvPath, "scenario CSV", errors);
  let snapshotSummary = { items: [] as SnapshotItem[], itemsSha256: null as string | null, imageCount: 0, maskCount: 0 };
  if (snapshotEvidence.text) {
    try {
      const parsed = JSON.parse(snapshotEvidence.text) as unknown;
      const tokenized = parseWithNumberTokens(snapshotEvidence.text);
      const document = record(parsed);
      const tokenizedDocument = record(tokenized);
      if (!document) errors.push("snapshot must be a JSON object");
      else snapshotSummary = validateSnapshot(document, tokenizedDocument?.items ?? [], errors);
    } catch (error) {
      errors.push(`cannot parse snapshot JSON: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  const instanceSummary = instanceEvidence.text
    ? parseInstanceRows(instanceEvidence.text, snapshotSummary.items, errors)
    : { records: [] as InstanceRecord[], rowCount: 0 };
  const scenarioSummary = scenarioEvidence.text
    ? parseScenarioRows(scenarioEvidence.text, snapshotSummary.imageCount, errors)
    : { groups: [] as ScenarioGroup[], rowCount: 0 };

  const records = instanceSummary.records;
  const directlyUsableRate = ratio(records.filter((item) => item.decision === "directly_usable").length, records.length);
  const contaminationInstanceRate = ratio(records.filter((item) => item.contaminated).length, records.length);
  const roughRectangleRate = ratio(records.filter((item) => item.roughRectangle).length, records.length);
  const pixelLeakageRate = ratio(
    records.reduce((sum, item) => sum + item.outsideGtPixels, 0),
    records.reduce((sum, item) => sum + item.predictedPixels, 0),
  );
  const missingRate = ratio(
    records.reduce((sum, item) => sum + item.missedGtPixels, 0),
    records.reduce((sum, item) => sum + item.gtPixels, 0),
  );
  if (records.length !== snapshotSummary.maskCount) errors.push("valid instance row count does not match snapshot mask count");
  if (directlyUsableRate === null || directlyUsableRate < DIRECTLY_USABLE_MINIMUM) errors.push(`directly usable rate must be at least ${DIRECTLY_USABLE_MINIMUM}`);
  if (contaminationInstanceRate === null || contaminationInstanceRate >= CONTAMINATION_MAXIMUM_EXCLUSIVE) errors.push(`contamination instance rate must be below ${CONTAMINATION_MAXIMUM_EXCLUSIVE}`);
  if (roughRectangleRate === null || roughRectangleRate > ROUGH_RECTANGLE_MAXIMUM) errors.push(`rough rectangle rate must be at most ${ROUGH_RECTANGLE_MAXIMUM}`);
  if (pixelLeakageRate === null) errors.push("pixel leakage rate cannot be computed from zero predicted pixels");
  if (missingRate === null || missingRate > MISSING_RATE_MAXIMUM) errors.push(`missing rate must be at most ${MISSING_RATE_MAXIMUM}`);

  const ok = errors.length === 0;
  return {
    version: RELEASE_PRODUCT_QUALITY_VERSION,
    generatedAt: new Date().toISOString(),
    ok,
    decision: ok ? "pass" : "hold",
    reviewedByUser: reviewer.length > 0,
    reviewer,
    trainingUse: "prohibited",
    snapshot: {
      path: snapshotPath,
      sha256: snapshotEvidence.sha256,
      itemsSha256: snapshotSummary.itemsSha256,
      imageCount: snapshotSummary.imageCount,
      maskCount: snapshotSummary.maskCount,
    },
    rawEvidence: {
      instances: { path: instancesCsvPath, sha256: instanceEvidence.sha256, rowCount: instanceSummary.rowCount },
      scenarios: { path: scenariosCsvPath, sha256: scenarioEvidence.sha256, rowCount: scenarioSummary.rowCount },
    },
    sampleImages: snapshotSummary.imageCount,
    sampleInstances: records.length,
    directlyUsableRate,
    contaminationInstanceRate,
    roughRectangleRate,
    pixelLeakageRate,
    missingRate,
    frozenMaximumMissingRate: MISSING_RATE_MAXIMUM,
    minimumAllowedDelta: MINIMUM_ALLOWED_DELTA,
    scenarioGroups: scenarioSummary.groups,
    errors,
  };
}

export async function verifyApprovedReleaseProductQualityReport(
  reportPath: string,
  expectedSnapshotPath: string,
): Promise<ApprovedReleaseProductQualityVerification> {
  let report: JsonRecord;
  try {
    report = await readJsonObject(path.resolve(reportPath));
  } catch (error) {
    return { found: false, ok: false, errors: [`cannot read product quality report: ${error instanceof Error ? error.message : String(error)}`], report: null, replay: null };
  }
  const errors: string[] = [];
  const snapshot = record(report.snapshot) ?? {};
  const rawEvidence = record(report.rawEvidence) ?? {};
  const instances = record(rawEvidence.instances) ?? {};
  const scenarios = record(rawEvidence.scenarios) ?? {};
  const snapshotPath = nonEmptyString(snapshot.path);
  const instancesCsvPath = nonEmptyString(instances.path);
  const scenariosCsvPath = nonEmptyString(scenarios.path);
  const reviewer = nonEmptyString(report.reviewer);
  if (report.version !== RELEASE_PRODUCT_QUALITY_VERSION) errors.push(`unsupported product quality report version ${String(report.version)}`);
  if (report.ok !== true || report.decision !== "pass") errors.push("product quality report is not passing");
  if (report.reviewedByUser !== true || !reviewer) errors.push("product quality report requires a named user reviewer");
  if (report.trainingUse !== "prohibited") errors.push("product quality report trainingUse must be prohibited");
  if (!Array.isArray(report.errors) || report.errors.length !== 0) errors.push("product quality report errors must be empty");
  if (!snapshotPath) errors.push("product quality report is missing snapshot.path");
  if (snapshotPath && !sameEvidencePath(snapshotPath, expectedSnapshotPath)) {
    errors.push("product quality report snapshot.path does not match expected frozen snapshot");
  }
  if (!instancesCsvPath) errors.push("product quality report is missing rawEvidence.instances.path");
  if (!scenariosCsvPath) errors.push("product quality report is missing rawEvidence.scenarios.path");

  let replay: ReleaseProductQualityReport | null = null;
  if (snapshotPath && instancesCsvPath && scenariosCsvPath && reviewer) {
    replay = await buildReleaseProductQualityEvidence({ snapshotPath, instancesCsvPath, scenariosCsvPath, reviewer });
    if (!replay.ok) errors.push(...replay.errors.map((error) => `replay: ${error}`));
    const fields = [
      "version", "ok", "decision", "reviewedByUser", "reviewer", "trainingUse", "snapshot", "rawEvidence",
      "sampleImages", "sampleInstances", "directlyUsableRate", "contaminationInstanceRate", "roughRectangleRate",
      "pixelLeakageRate", "missingRate", "frozenMaximumMissingRate", "minimumAllowedDelta", "scenarioGroups", "errors",
    ];
    for (const field of fields) {
      if (JSON.stringify(report[field]) !== JSON.stringify(replay[field])) errors.push(`product quality report ${field} does not match replay`);
    }
  }
  return { found: true, ok: errors.length === 0, errors, report, replay };
}
