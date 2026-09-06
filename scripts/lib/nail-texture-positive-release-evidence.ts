import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { compareReleaseIdentity, type NailTextureReleaseIdentity } from "./nail-texture-release-identity.ts";

type Binding = { path: string; sha256: string };

const sha256 = (bytes: Buffer | string) => createHash("sha256").update(bytes).digest("hex");
const canonicalSha256 = (value: unknown) => sha256(JSON.stringify(sortCanonical(value)));

function sortCanonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortCanonical);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, sortCanonical(child)]));
}

function object(value: unknown): Record<string, any> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : null;
}

function binding(value: unknown, label: string, errors: string[]): Binding | null {
  const record = object(value);
  if (!record || Object.keys(record).sort().join(",") !== "path,sha256") {
    errors.push(`${label} binding is invalid`);
    return null;
  }
  if (typeof record.path !== "string" || !path.isAbsolute(record.path) || typeof record.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(record.sha256)) {
    errors.push(`${label} binding is invalid`);
    return null;
  }
  return { path: record.path, sha256: record.sha256 };
}

export function validatePositiveRecognitionReport(report: unknown, identity: NailTextureReleaseIdentity): string[] {
  const errors: string[] = [];
  const value = object(report);
  if (!value) return ["positive recognition report must be an object"];
  errors.push(...compareReleaseIdentity(identity, value.releaseIdentity, "positive recognition report"));
  if (value.schemaVersion !== 3) errors.push("positive recognition report schemaVersion must be 3");
  if (value.ok !== true || value.decision !== "accept_positive_recognition_gate" || value.trainingUse !== "prohibited") {
    errors.push("positive recognition report is not an accepted training-prohibited release report");
  }
  const contract = object(value.deploymentContract);
  const expectedContract: Record<string, unknown> = {
    imgsz: 512,
    scoreThreshold: identity.core.scoreThreshold,
    matchIou: 0.5,
    completeMaskIou: 0.75,
    minimumImages: 100,
    minimumInstanceRecall: 0.9,
    minimumCompleteMaskRatio: 0.85,
    maximumMissingImageRate: 0.1,
    maximumWeightedSpuriousRate: 0.02,
  };
  for (const [key, expected] of Object.entries(expectedContract)) if (contract?.[key] !== expected) errors.push(`positive recognition contract ${key} must equal ${expected}`);
  if (JSON.stringify(contract?.spuriousWeights) !== JSON.stringify({ duplicates: 1, invalidPredictionMasks: 1.5, falsePositives: 2 })) {
    errors.push("positive recognition spurious weights are not the fixed release contract");
  }
  const gates = object(value.gates);
  for (const key of ["minimumImages", "instanceRecall", "completeMaskRatio", "missingImageRate", "weightedSpuriousRate", "everyImageHasModelOutput"]) {
    if (gates?.[key] !== true) errors.push(`positive recognition gate ${key} is not PASS`);
  }
  const summary = object(value.summary);
  if (!summary || summary.images < 100 || summary.instanceRecall < 0.9 || summary.completeMaskRatio < 0.85 || summary.missingImageRate > 0.1 || summary.weightedSpuriousRate > 0.02) {
    errors.push("positive recognition summary does not satisfy the fixed release contract");
  }
  const items = value.items;
  if (!Array.isArray(items) || items.length !== summary?.images || canonicalSha256(items) !== value.itemsSha256) {
    errors.push("positive recognition per-image evidence is incomplete or has drifted");
  }
  const candidate = object(value.candidate);
  const modelHashes = new Set(identity.core.modelFiles.map((item) => item.sha256));
  if (!candidate || !modelHashes.has(candidate.weightsSha256) || candidate.runtimeSelectionLockSha256 !== identity.core.runtimeSelectionLockSha256) {
    errors.push("positive recognition candidate does not match releaseIdentity");
  }
  return errors;
}

export function validatePositiveConsumptionLedger(
  ledger: unknown,
  identity: NailTextureReleaseIdentity,
  report: Record<string, any>,
): string[] {
  const errors: string[] = [];
  const value = object(ledger);
  if (!value) return ["positive holdout consumption ledger must be an object"];
  errors.push(...compareReleaseIdentity(identity, value.releaseIdentity, "positive holdout consumption ledger"));
  if (value.schemaVersion !== 1 || value.decision !== "positive_release_holdout_one_use_ledger" || value.purpose !== "positive-recognition-release-evaluation") {
    errors.push("positive holdout consumption ledger contract is invalid");
  }
  const inputs = object(report.inputs);
  const snapshot = object(value.snapshot);
  if (!snapshot || path.resolve(snapshot.path ?? "") !== path.resolve(inputs?.snapshotManifest ?? "") || snapshot.sha256 !== inputs?.snapshotManifestSha256) {
    errors.push("positive holdout ledger snapshot differs from the recognition report");
  }
  const runtimeLock = object(value.runtimeSelectionLock);
  if (!runtimeLock || runtimeLock.sha256 !== identity.core.runtimeSelectionLockSha256) {
    errors.push("positive holdout ledger runtime lock differs from releaseIdentity");
  }
  const attempts = value.attempts;
  if (!Array.isArray(attempts) || attempts.length < 1) return [...errors, "positive holdout consumption attempts are missing"];
  for (const [index, attemptValue] of attempts.entries()) {
    const attempt = object(attemptValue);
    if (!attempt || attempt.attempt !== index + 1) errors.push(`positive holdout attempt ${index + 1} is invalid`);
    else if (index < attempts.length - 1 && attempt.state !== "aborted-no-data-read") errors.push("only a no-data-read abort may precede a retry");
  }
  const finalAttempt = object(attempts.at(-1));
  if (finalAttempt?.state !== "completed") errors.push("positive holdout consumption is not completed");
  const expectedEvents = ["claimed", "image-read-started", "prediction-started", "completed"];
  if (!Array.isArray(finalAttempt?.events) || JSON.stringify(finalAttempt.events.map((item: any) => item?.type)) !== JSON.stringify(expectedEvents)) {
    errors.push("positive holdout final attempt event order is invalid");
  }
  const artifact = object(finalAttempt?.artifactIndex);
  if (!artifact || path.resolve(artifact.path ?? "") !== path.resolve(inputs?.artifactIndex ?? "") || artifact.sha256 !== inputs?.artifactIndexSha256) {
    errors.push("positive holdout ledger artifact index differs from the recognition report");
  }
  return errors;
}

export async function verifyPositiveReleaseEvidence(profile: {
  ok: boolean;
  status: string;
  releaseIdentity: NailTextureReleaseIdentity | null;
  reportBindings: Record<string, unknown> | null;
}) {
  const transitivePaths: string[] = [];
  if (!profile.ok || !profile.releaseIdentity || !profile.reportBindings) {
    const error = profile.status === "no_approved_release_candidate" ? "no approved releaseIdentity exists" : "releaseIdentity profile is invalid";
    return {
      quality: { ok: false, status: profile.status, errors: [error] },
      consumption: { ok: false, status: profile.status, errors: [error] },
      transitivePaths,
    };
  }
  const qualityErrors: string[] = [];
  const reportBinding = binding(profile.reportBindings.positiveRecognitionQuality, "positiveRecognitionQuality", qualityErrors);
  let report: Record<string, any> | null = null;
  if (reportBinding) {
    transitivePaths.push(reportBinding.path);
    try {
      const bytes = await readFile(reportBinding.path);
      if (sha256(bytes) !== reportBinding.sha256) qualityErrors.push("positive recognition report hash drift");
      report = object(JSON.parse(bytes.toString("utf8")));
      qualityErrors.push(...validatePositiveRecognitionReport(report, profile.releaseIdentity));
    } catch (error) {
      qualityErrors.push(`positive recognition report cannot be read: ${String(error)}`);
    }
  }
  if (reportBinding && qualityErrors.length === 0) {
    const verification = spawnSync("python", [path.resolve("model/training/build-positive-recognition-quality-report.py"), "--verify-report", reportBinding.path], {
      encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" }, windowsHide: true,
    });
    if (verification.status !== 0) qualityErrors.push(`positive recognition deep replay failed: ${(verification.stderr || verification.stdout).trim()}`);
  }
  const consumptionErrors: string[] = [];
  const ledgerBinding = binding(object(report?.inputs)?.consumptionLedger && {
    path: object(report?.inputs)?.consumptionLedger,
    sha256: object(report?.inputs)?.consumptionLedgerSha256,
  }, "positive holdout consumption ledger", consumptionErrors);
  let ledger: Record<string, any> | null = null;
  if (ledgerBinding) {
    transitivePaths.push(ledgerBinding.path);
    try {
      const bytes = await readFile(ledgerBinding.path);
      if (sha256(bytes) !== ledgerBinding.sha256) consumptionErrors.push("positive holdout consumption ledger hash drift");
      ledger = object(JSON.parse(bytes.toString("utf8")));
      if (report) consumptionErrors.push(...validatePositiveConsumptionLedger(ledger, profile.releaseIdentity, report));
    } catch (error) {
      consumptionErrors.push(`positive holdout consumption ledger cannot be read: ${String(error)}`);
    }
  }
  if (ledgerBinding && consumptionErrors.length === 0) {
    const verification = spawnSync("python", [path.resolve("model/training/positive-release-consumption-ledger.py"), "--action", "verify", "--ledger", ledgerBinding.path], {
      encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" }, windowsHide: true,
    });
    if (verification.status !== 0) consumptionErrors.push(`positive holdout consumption ledger deep replay failed: ${(verification.stderr || verification.stdout).trim()}`);
  }
  return {
    quality: { ok: qualityErrors.length === 0, status: qualityErrors.length === 0 ? "approved" : "invalid", reportPath: reportBinding?.path ?? null, errors: qualityErrors },
    consumption: { ok: consumptionErrors.length === 0, status: consumptionErrors.length === 0 ? "consumed_once" : "invalid", ledgerPath: ledgerBinding?.path ?? null, errors: consumptionErrors },
    transitivePaths,
  };
}
