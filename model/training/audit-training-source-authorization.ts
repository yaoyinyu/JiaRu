import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import {
  parseSourceRecords,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

type AuthorizationMode = "internal" | "release";

interface AuthorizationIssue {
  code:
    | "missing_sources_csv"
    | "empty_sources_csv"
    | "missing_origin_ref"
    | "missing_license"
    | "release_web_source_not_allowed"
    | "release_internal_test_license"
    | "release_ambiguous_license"
    | "release_user_without_authorization"
    | "release_merchant_without_authorization";
  severity: "error" | "warning";
  message: string;
  imageId?: string;
  fileName?: string;
  originType?: SourceRecord["originType"];
  license?: string;
}

interface AuthorizationReport {
  datasetRoot: string;
  sourcesCsvPath: string;
  reportPath: string;
  mode: AuthorizationMode;
  recordCount: number;
  counts: {
    byOriginType: Record<string, number>;
    byLicense: Record<string, number>;
  };
  ok: boolean;
  issues: AuthorizationIssue[];
}

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);

function readArg(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  if (index === -1) return undefined;
  return process.argv[index + 1];
}

function readMode(): AuthorizationMode {
  const raw = readArg("--mode") ?? process.env.AUTHORIZATION_MODE ?? "release";
  if (raw === "internal" || raw === "release") return raw;
  throw new Error(`Unsupported --mode ${raw}. Use internal or release.`);
}

function normalizeLicense(license: string): string {
  return license.trim().toLowerCase();
}

function includesAny(value: string, tokens: string[]): boolean {
  return tokens.some((token) => value.includes(token));
}

function isExplicitlyTrainable(license: string): boolean {
  const normalized = normalizeLicense(license);
  return includesAny(normalized, [
    "user-authorized",
    "merchant-authorized",
    "owner-authorized",
    "training-authorized",
    "commercial",
    "licensed",
    "cc0",
    "public-domain",
    "public domain",
    "internal-training",
  ]);
}

function isInternalTestOnly(license: string): boolean {
  const normalized = normalizeLicense(license);
  return includesAny(normalized, [
    "internal-test-only",
    "internal-test",
    "test-only",
    "verification-only",
    "demo-only",
  ]);
}

function countBy(records: SourceRecord[], selector: (record: SourceRecord) => string) {
  return records.reduce<Record<string, number>>((counts, record) => {
    const key = selector(record).trim() || "(empty)";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

function auditRecord(record: SourceRecord, mode: AuthorizationMode): AuthorizationIssue[] {
  const issues: AuthorizationIssue[] = [];
  const license = normalizeLicense(record.license);

  if (!record.originRef.trim()) {
    issues.push({
      code: "missing_origin_ref",
      severity: mode === "release" ? "error" : "warning",
      message:
        "originRef must record the source URL, upload batch, contract, or authorization note before training.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
  }

  if (!license) {
    issues.push({
      code: "missing_license",
      severity: mode === "release" ? "error" : "warning",
      message: "license must describe usage permission before the image can enter training.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
    return issues;
  }

  if (mode === "internal") {
    return issues;
  }

  if (record.originType === "web") {
    issues.push({
      code: "release_web_source_not_allowed",
      severity: "error",
      message:
        "web-sourced images are blocked for release training unless reclassified with explicit owner authorization.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
  }

  if (isInternalTestOnly(record.license)) {
    issues.push({
      code: "release_internal_test_license",
      severity: "error",
      message:
        "internal-test-only material can be used for verification, but not for release training.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
  }

  if (record.originType === "user" && !includesAny(license, ["user-authorized", "owner-authorized", "training-authorized"])) {
    issues.push({
      code: "release_user_without_authorization",
      severity: "error",
      message:
        "user uploads need explicit user/owner/training authorization before release training.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
  }

  if (record.originType === "merchant" && !includesAny(license, ["merchant-authorized", "owner-authorized", "training-authorized", "commercial", "licensed"])) {
    issues.push({
      code: "release_merchant_without_authorization",
      severity: "error",
      message:
        "merchant materials need explicit merchant/owner/commercial authorization before release training.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
  }

  if (!isExplicitlyTrainable(record.license)) {
    issues.push({
      code: "release_ambiguous_license",
      severity: "error",
      message:
        "license is not explicit enough for release training. Use user-authorized, merchant-authorized, commercial, licensed, cc0, public-domain, or internal-training wording.",
      imageId: record.imageId,
      fileName: record.fileName,
      originType: record.originType,
      license: record.license,
    });
  }

  return issues;
}

async function main() {
  const mode = readMode();
  const metadataDir = path.join(datasetRoot, "metadata");
  const sourcesCsvPath = path.resolve(
    readArg("--sources") ?? path.join(metadataDir, "sources.csv")
  );
  const reportPath = path.resolve(
    readArg("--output") ??
      path.join(metadataDir, `training-source-authorization-${mode}.json`)
  );

let records: SourceRecord[] = [];
  const issues: AuthorizationIssue[] = [];
  try {
    records = parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    issues.push({
      code: "missing_sources_csv",
      severity: "error",
      message:
        "sources.csv does not exist. Create or synchronize source metadata before training authorization can pass.",
    });
  }
if (records.length === 0 && !issues.some((issue) => issue.code === "missing_sources_csv")) {
    issues.push({
      code: "empty_sources_csv",
      severity: "error",
      message:
        "sources.csv contains no source records. Authorization cannot pass without reviewed source metadata.",
    });
  }
  issues.push(...records.flatMap((record) => auditRecord(record, mode)));
  const report: AuthorizationReport = {
    datasetRoot,
    sourcesCsvPath,
    reportPath,
    mode,
    recordCount: records.length,
    counts: {
      byOriginType: countBy(records, (record) => record.originType),
      byLicense: countBy(records, (record) => normalizeLicense(record.license)),
    },
    ok: issues.every((issue) => issue.severity !== "error"),
    issues,
  };

  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
