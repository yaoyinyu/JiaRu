import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  writePatternTestPng,
  writeTestPng,
} from "./helpers/hard-negative-evidence.ts";
import { createFormalThresholdEvidence } from "./helpers/formal-threshold-evidence.ts";

const recorder = path.resolve(
  "model/training/record-independent-hard-negative-authorization.py",
);
const python = process.env.PYTHON ?? "python";
const freezeDirectory = "_independent_holdout_freeze_v1";
let thresholdEvidence:
  | ReturnType<typeof createFormalThresholdEvidence>
  | undefined;

function getThresholdEvidence() {
  thresholdEvidence ??= createFormalThresholdEvidence(0.45);
  return thresholdEvidence;
}

function writeJson(file: string, value: unknown) {
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function makeBatch(count = 100) {
  const root = mkdtempSync(path.join(tmpdir(), "independent-hard-negative-auth-"));
  const images = path.join(root, "images");
  const authorization = path.join(root, "user-authorization.json");
  const { weights, thresholdReport, scoreThreshold } = getThresholdEvidence();
  const confirmationNote = "用户明确允许该精确批次用于独立发布测试。";
  writeJson(authorization, {
    schemaVersion: 1,
    ok: true,
    decision: "authorized_for_independent_holdout_evaluation",
    confirmedBy: "workspace-user",
    confirmationNote,
    authorizationEvidence: {
      kind: "codex-user-message",
      threadId: "019f4ca0-a894-7b63-8ec9-c286885a5a22",
      decisionId:
        "goal-thread/019f4ca0-a894-7b63-8ec9-c286885a5a22/test-authorization",
      userMessageText: confirmationNote,
      userMessageSha256: createHash("sha256")
        .update(confirmationNote)
        .digest("hex"),
    },
    sourceRoot: images,
    scopeIncludesDescendants: false,
    authorizedUses: [
      "independent-release-test",
      "long-term-regression",
      "model-diagnostic-evaluation",
      "data-quality-review",
    ],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
  });
  for (let index = 0; index < count; index++) {
    const sequence = 161 + index;
    const shard = `shard-${String.fromCharCode(97 + (index % 3))}`;
    const fileName =
      `hard_negative_independent_20260724_${String(sequence).padStart(3, "0")}_` +
      `fixture_family_${String((index % 99) + 1).padStart(2, "0")}.png`;
    writePatternTestPng(path.join(images, shard, fileName), sequence);
  }
  return {
    root,
    images,
    authorization,
    weights,
    thresholdReport,
    scoreThreshold,
  };
}

function runRecorder(item: ReturnType<typeof makeBatch>) {
  return spawnSync(
    python,
    [
      recorder,
      "--source-root",
      item.images,
      "--user-authorization",
      item.authorization,
      "--candidate-weights",
      item.weights,
      "--candidate-threshold-report",
      item.thresholdReport,
      "--batch-date",
      "20260724",
      "--sequence-start",
      "161",
      "--sequence-end",
      "260",
    ],
    { encoding: "utf8" },
  );
}

test("atomically freezes a pre-authorized recursive 100-image batch", () => {
  const item = makeBatch();
  const result = runRecorder(item);
  assert.equal(result.status, 0, result.stderr);

  const evidence = path.join(item.images, freezeDirectory);
  const machineAudit = JSON.parse(
    readFileSync(path.join(evidence, "machine-audit-v1.json"), "utf8"),
  );
  const authorization = JSON.parse(
    readFileSync(path.join(evidence, "authorization-record-A-v1.json"), "utf8"),
  );
  const freeze = JSON.parse(
    readFileSync(path.join(evidence, "freeze-manifest-v1.json"), "utf8"),
  );
  assert.equal(machineAudit.ok, true);
  assert.equal(machineAudit.decodedCount, 100);
  assert.equal(machineAudit.nearDuplicateThreshold, 12);
  assert.equal(machineAudit.nearDuplicatePairs.length, 0);
  assert.equal(machineAudit.records.length, 100);
  assert.match(machineAudit.records[0].relativePath, /^shard-[abc]\//);
  assert.equal(authorization.decision, "A");
  assert.equal(authorization.currentTrainingUse, "prohibited");
  assert.equal(authorization.summary.authorizedImages, 100);
  assert.equal(authorization.summary.qualityApprovedImages, 0);
  assert.equal(authorization.entries.length, 100);
  assert.ok(
    authorization.entries.every(
      (entry: { trainingEligibility: string }) =>
        entry.trainingEligibility === "prohibited-independent-holdout-only",
    ),
  );
  assert.equal(
    freeze.decision,
    "independent_holdout_frozen_before_authorized_inference",
  );
  assert.equal(freeze.trainingUse, "prohibited");
  assert.equal(freeze.batchIdentity.sequenceStart, 161);
  assert.equal(freeze.batchIdentity.sequenceEnd, 260);
  assert.equal(freeze.batchIdentity.candidateScoreThreshold, 0.45);

  const verified = spawnSync(
    python,
    [
      recorder,
      "--verify-freeze",
      path.join(evidence, "freeze-manifest-v1.json"),
    ],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);
  assert.equal(JSON.parse(verified.stdout).imageCount, 100);
  assert.equal(JSON.parse(verified.stdout).candidateScoreThreshold, 0.45);

  const repeated = runRecorder(item);
  assert.notEqual(repeated.status, 0);
  assert.match(repeated.stderr, /frozen evidence already exists and is immutable/);
});

test("refuses an undersized or non-contiguous batch without final evidence", () => {
  const item = makeBatch(99);
  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /expected=100 actual=99/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("fixed perceptual duplicate gate rejects visually identical re-encodings", () => {
  const item = makeBatch();
  const first = path.join(
    item.images,
    "shard-a",
    "hard_negative_independent_20260724_161_fixture_family_01.png",
  );
  const second = path.join(
    item.images,
    "shard-b",
    "hard_negative_independent_20260724_162_fixture_family_02.png",
  );
  writeTestPng(first, 1);
  writeTestPng(second, 2);

  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /perceptual near-duplicate gate failed.*pairs=/s);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects authorization that does not independently cover holdout use", () => {
  const item = makeBatch();
  const authorization = JSON.parse(readFileSync(item.authorization, "utf8"));
  authorization.authorizedUses = ["long-term-regression"];
  writeJson(item.authorization, authorization);

  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /authorizedUses must exactly equal/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects mixed independent-holdout and commercial-training uses", () => {
  const item = makeBatch();
  const authorization = JSON.parse(readFileSync(item.authorization, "utf8"));
  authorization.authorizedUses.push("commercial-model-training");
  writeJson(item.authorization, authorization);

  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /authorizedUses must exactly equal/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects a broad parent authorization instead of an exact batch binding", () => {
  const item = makeBatch();
  const authorization = JSON.parse(readFileSync(item.authorization, "utf8"));
  authorization.sourceRoot = item.root;
  authorization.scopeIncludesDescendants = true;
  writeJson(item.authorization, authorization);

  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(
    result.stderr,
    /sourceRoot must exactly match the frozen batch root/,
  );
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects junction or symbolic-link entries before recursive enumeration", (t) => {
  const item = makeBatch();
  const outside = path.join(item.root, "outside-linked-directory");
  const linked = path.join(item.images, "linked-directory");
  mkdirSync(outside);
  try {
    symlinkSync(outside, linked, process.platform === "win32" ? "junction" : "dir");
  } catch (error) {
    t.skip(`link creation is unavailable in this environment: ${String(error)}`);
    return;
  }

  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(
    result.stderr,
    /symbolic link, junction, or reparse-point entry is prohibited/,
  );
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});
