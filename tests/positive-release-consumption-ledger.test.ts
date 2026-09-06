import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { validatePositiveConsumptionLedger, validatePositiveRecognitionReport } from "../scripts/lib/nail-texture-positive-release-evidence.ts";
import type { NailTextureReleaseIdentity } from "../scripts/lib/nail-texture-release-identity.ts";

const python = process.env.PYTHON || "python";
const script = path.resolve("model/training/positive-release-consumption-ledger.py");
const sha = (bytes: Buffer | string) => createHash("sha256").update(bytes).digest("hex");
const canonical = (value: unknown): string => {
  const sort = (input: unknown): unknown => Array.isArray(input) ? input.map(sort) : input && typeof input === "object"
    ? Object.fromEntries(Object.entries(input as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, sort(child)]))
    : input;
  return sha(JSON.stringify(sort(value)));
};

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "positive-release-ledger-"));
  const lock = path.join(root, "runtime-lock.json");
  const manifest = path.join(root, "manifest.json");
  const artifact = path.join(root, "artifacts.json");
  const identityPath = path.join(root, "release-identity.json");
  const ledger = path.join(root, "consumption-ledger.json");
  writeFileSync(lock, "{}\n");
  writeFileSync(artifact, "{}\n");
  const items = [{ fileName: "a.png", imageSha256: "a".repeat(64), trainingUse: "prohibited" }];
  writeFileSync(manifest, JSON.stringify({ trainingUse: "prohibited", itemsSha256: canonical(items), items }, null, 2) + "\n");
  const core = {
    candidateId: "candidate-58", runtimeSelectionLockSha256: sha(readFileSync(lock)),
    modelFiles: [{ role: "segment", sha256: "b".repeat(64) }], inputSize: 512, scoreThreshold: 0.4,
    combinationRulesSha256: "c".repeat(64), preprocessSha256: "d".repeat(64), postprocessSha256: "e".repeat(64),
  };
  const identity: NailTextureReleaseIdentity = { core, coreSha256: canonical(core), manifestSha256: "f".repeat(64) };
  writeFileSync(identityPath, JSON.stringify({ releaseIdentity: identity }, null, 2) + "\n");
  return { root, lock, manifest, artifact, identityPath, ledger, identity };
}

function run(args: string[]) {
  return JSON.parse(execFileSync(python, [script, ...args], { encoding: "utf8" }));
}

test("正样本发布留出必须先原子认领且活动认领不可重复", () => {
  const item = fixture();
  try {
    const claimed = run(["--action", "claim", "--ledger", item.ledger, "--release-identity", item.identityPath, "--snapshot-manifest", item.manifest, "--runtime-selection-lock", item.lock]);
    assert.equal(claimed.state, "claimed");
    const duplicate = spawnSync(python, [script, "--action", "claim", "--ledger", item.ledger, "--release-identity", item.identityPath, "--snapshot-manifest", item.manifest, "--runtime-selection-lock", item.lock], { encoding: "utf8" });
    assert.equal(duplicate.status, 2);
    assert.match(duplicate.stderr, /retry is forbidden/);
  } finally { rmSync(item.root, { recursive: true, force: true }); }
});

test("仅未读图失败允许重试，读图后必须完成且永久禁止再次消费", () => {
  const item = fixture();
  try {
    const first = run(["--action", "claim", "--ledger", item.ledger, "--release-identity", item.identityPath, "--snapshot-manifest", item.manifest, "--runtime-selection-lock", item.lock]);
    run(["--action", "abort-no-data-read", "--ledger", item.ledger, "--run-id", first.runId, "--reason", "worker bootstrap failed"]);
    const second = run(["--action", "claim", "--ledger", item.ledger, "--release-identity", item.identityPath, "--snapshot-manifest", item.manifest, "--runtime-selection-lock", item.lock]);
    run(["--action", "mark-read", "--ledger", item.ledger, "--run-id", second.runId]);
    const abortAfterRead = spawnSync(python, [script, "--action", "abort-no-data-read", "--ledger", item.ledger, "--run-id", second.runId, "--reason", "late failure"], { encoding: "utf8" });
    assert.equal(abortAfterRead.status, 2);
    run(["--action", "mark-prediction", "--ledger", item.ledger, "--run-id", second.runId]);
    run(["--action", "complete", "--ledger", item.ledger, "--run-id", second.runId, "--artifact-index", item.artifact]);
    const verified = run(["--action", "verify", "--ledger", item.ledger]);
    assert.equal(verified.state, "completed");
    assert.equal(verified.attempts, 2);
    const consumedAgain = spawnSync(python, [script, "--action", "claim", "--ledger", item.ledger, "--release-identity", item.identityPath, "--snapshot-manifest", item.manifest, "--runtime-selection-lock", item.lock], { encoding: "utf8" });
    assert.equal(consumedAgain.status, 2);
  } finally { rmSync(item.root, { recursive: true, force: true }); }
});

test("固定逐实例合同和台账必须绑定同一releaseIdentity、快照与预测制品", () => {
  const item = fixture();
  try {
    const claim = run(["--action", "claim", "--ledger", item.ledger, "--release-identity", item.identityPath, "--snapshot-manifest", item.manifest, "--runtime-selection-lock", item.lock]);
    run(["--action", "mark-read", "--ledger", item.ledger, "--run-id", claim.runId]);
    run(["--action", "mark-prediction", "--ledger", item.ledger, "--run-id", claim.runId]);
    run(["--action", "complete", "--ledger", item.ledger, "--run-id", claim.runId, "--artifact-index", item.artifact]);
    const ledger = JSON.parse(readFileSync(item.ledger, "utf8"));
    const items = Array.from({ length: 100 }, (_, index) => ({ stem: String(index), predictionCount: 1 }));
    const report = {
      schemaVersion: 3, ok: true, decision: "accept_positive_recognition_gate", trainingUse: "prohibited", releaseIdentity: item.identity,
      deploymentContract: { imgsz: 512, scoreThreshold: 0.4, matchIou: 0.5, completeMaskIou: 0.75, minimumImages: 100, minimumInstanceRecall: 0.9, minimumCompleteMaskRatio: 0.85, maximumMissingImageRate: 0.1, maximumWeightedSpuriousRate: 0.02, spuriousWeights: { duplicates: 1, invalidPredictionMasks: 1.5, falsePositives: 2 } },
      candidate: { weightsSha256: "b".repeat(64), runtimeSelectionLockSha256: sha(readFileSync(item.lock)) },
      summary: { images: 100, instanceRecall: 0.95, completeMaskRatio: 0.9, missingImageRate: 0.05, weightedSpuriousRate: 0.01 },
      gates: { minimumImages: true, instanceRecall: true, completeMaskRatio: true, missingImageRate: true, weightedSpuriousRate: true, everyImageHasModelOutput: true },
      items, itemsSha256: canonical(items),
      inputs: { snapshotManifest: item.manifest, snapshotManifestSha256: sha(readFileSync(item.manifest)), artifactIndex: item.artifact, artifactIndexSha256: sha(readFileSync(item.artifact)) },
    };
    assert.deepEqual(validatePositiveRecognitionReport(report, item.identity), []);
    assert.deepEqual(validatePositiveConsumptionLedger(ledger, item.identity, report), []);
    report.deploymentContract.maximumWeightedSpuriousRate = 0.03;
    assert.match(validatePositiveRecognitionReport(report, item.identity).join("\n"), /maximumWeightedSpuriousRate/);
    writeFileSync(item.artifact, "drift\n");
    const verify = spawnSync(python, [script, "--action", "verify", "--ledger", item.ledger], { encoding: "utf8" });
    assert.equal(verify.status, 2);
    assert.match(verify.stderr, /drifted/);
  } finally { rmSync(item.root, { recursive: true, force: true }); }
});
