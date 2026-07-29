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
  thresholdEvidence ??= createFormalThresholdEvidence(0.5);
  return thresholdEvidence;
}

function writeJson(file: string, value: unknown) {
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
};

const canonicalSha = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");

function makeProtectedRegistry(
  root: string,
  options: {
    sourceIdentityCollision?: boolean;
    exactCollisionImage?: string;
    exactCollisionRole?: "training" | "holdout";
    perceptualCollisionImage?: string;
  } = {},
) {
  const manifests: string[] = [];
  const protectedImages: string[] = [];
  for (const [index, role] of ["training", "independent"].entries()) {
    const fileName =
      `hard_negative_${role}_20260723_${role === "training" ? "101" : "201"}_` +
      `protected_${role}_01.png`;
    const imagePath = path.join(root, "protected", role, fileName);
    const registryRole = role === "training" ? "training" : "holdout";
    if (
      options.exactCollisionImage &&
      (options.exactCollisionRole ?? "training") === registryRole
    ) {
      mkdirSync(path.dirname(imagePath), { recursive: true });
      writeFileSync(imagePath, readFileSync(options.exactCollisionImage));
    } else if (index === 0 && options.perceptualCollisionImage) {
      mkdirSync(path.dirname(imagePath), { recursive: true });
      writeFileSync(
        imagePath,
        Buffer.concat([
          readFileSync(options.perceptualCollisionImage),
          Buffer.from("perceptual-reencoding-fixture"),
        ]),
      );
    } else {
      writePatternTestPng(imagePath, 5001 + index);
    }
    protectedImages.push(imagePath);
    const sourceGroup =
      index === 0 && options.sourceIdentityCollision
        ? "ai-hard-negative-training-2026-07-24:fixture_family"
        : `ai-hard-negative-${role}-2026-07-23:protected_${role}`;
    const items = [
      {
        fileName,
        sourceFileName: fileName,
        sourceGroup,
        imageSha256: shaFile(imagePath),
        imagePath,
        width: 320,
        height: 320,
        imageFormat: "PNG",
        role: role === "training" ? "hard-negative" : "independent-holdout",
        originalResolutionVisualReview: true,
        trainingUse: role === "training" ? "permitted" : "prohibited",
      },
    ];
    const manifest = path.join(root, `protected-${role}.json`);
    writeJson(manifest, {
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision:
        role === "training"
          ? "approved_hard_negative_manifest"
          : "approved_independent_hard_negative_holdout",
      trainingUse: role === "training" ? "permitted" : "prohibited",
      itemsSha256: canonicalSha(items),
      items,
    });
    manifests.push(manifest);
  }
  const registry = path.join(root, "protected-registry.json");
  const entries = manifests.map((manifest, index) => ({
    path: path.resolve(manifest),
    sha256: shaFile(manifest),
    role: index === 0 ? "training" : "holdout",
  }));
  writeJson(registry, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: 2,
      trainingManifestCount: 1,
      holdoutManifestCount: 1,
    },
    entriesSha256: canonicalSha(entries),
    entries,
  });
  return { registry, manifests, protectedImages };
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
  const protectedRegistry = makeProtectedRegistry(root);
  return {
    root,
    images,
    authorization,
    weights,
    thresholdReport,
    scoreThreshold,
    protectedRegistry,
  };
}

function runRecorder(
  item: ReturnType<typeof makeBatch>,
  options: { omitRegistry?: boolean; registry?: string } = {},
) {
  const registryArgs = options.omitRegistry
    ? []
    : [
        "--protected-hard-negative-registry",
        options.registry ?? item.protectedRegistry.registry,
      ];
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
      "--expected-candidate-weights-sha256",
      shaFile(item.weights),
      "--expected-score-threshold",
      String(item.scoreThreshold),
      ...registryArgs,
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
  assert.equal(freeze.batchIdentity.candidateScoreThreshold, 0.5);
  assert.equal(
    freeze.inputs.protectedHardNegativeRegistry.sha256,
    shaFile(item.protectedRegistry.registry),
  );
  assert.equal(
    freeze.protectedHardNegativeCrossCheck.exactSha256Matches,
    0,
  );
  assert.equal(
    freeze.protectedHardNegativeCrossCheck.sourceIdentityMatches,
    0,
  );
  assert.equal(
    freeze.protectedHardNegativeCrossCheck.perceptualMatchesAtOrBelowThreshold,
    0,
  );

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
  assert.equal(JSON.parse(verified.stdout).candidateScoreThreshold, 0.5);
  assert.equal(
    JSON.parse(verified.stdout).protectedHardNegativeRegistry.sha256,
    shaFile(item.protectedRegistry.registry),
  );

  const repeated = runRecorder(item);
  assert.notEqual(repeated.status, 0);
  assert.match(repeated.stderr, /frozen evidence already exists and is immutable/);
});

test("requires a protected hard-negative registry for every new freeze", () => {
  const item = makeBatch();
  const result = runRecorder(item, { omitRegistry: true });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /--protected-hard-negative-registry/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("verify-freeze deeply rejects protected registry drift and omission", () => {
  const item = makeBatch();
  const frozen = runRecorder(item);
  assert.equal(frozen.status, 0, frozen.stderr);
  const manifestPath = path.join(
    item.images,
    freezeDirectory,
    "freeze-manifest-v1.json",
  );

  writeFileSync(item.protectedRegistry.registry, "{}\n");
  const drifted = spawnSync(
    python,
    [recorder, "--verify-freeze", manifestPath],
    { encoding: "utf8" },
  );
  assert.notEqual(drifted.status, 0);
  assert.match(drifted.stderr, /registry.*SHA-256.*drift|registry binding drift/is);

  const freeze = JSON.parse(readFileSync(manifestPath, "utf8"));
  delete freeze.inputs.protectedHardNegativeRegistry;
  delete freeze.inputs.protectedHardNegativeManifests;
  writeJson(manifestPath, freeze);
  const omitted = spawnSync(
    python,
    [recorder, "--verify-freeze", manifestPath],
    { encoding: "utf8" },
  );
  assert.notEqual(omitted.status, 0);
  assert.match(omitted.stderr, /omits the protected hard-negative registry binding/);
});

test("rejects exact SHA-256 overlap with protected training evidence", () => {
  const item = makeBatch();
  const candidate = path.join(
    item.images,
    "shard-a",
    "hard_negative_independent_20260724_161_fixture_family_01.png",
  );
  const protectedRegistry = makeProtectedRegistry(item.root, {
    exactCollisionImage: candidate,
  });
  const result = runRecorder(item, { registry: protectedRegistry.registry });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /exactly duplicates a protected hard negative/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects reuse of an old independent holdout protected by the registry", () => {
  const item = makeBatch();
  const candidate = path.join(
    item.images,
    "shard-a",
    "hard_negative_independent_20260724_161_fixture_family_01.png",
  );
  const protectedRegistry = makeProtectedRegistry(item.root, {
    exactCollisionImage: candidate,
    exactCollisionRole: "holdout",
  });
  const result = runRecorder(item, { registry: protectedRegistry.registry });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /exactly duplicates a protected hard negative/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects an operator-declared candidate identity mismatch before freezing", () => {
  const item = makeBatch();
  const wrongWeights = spawnSync(
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
      "--expected-candidate-weights-sha256",
      "0".repeat(64),
      "--expected-score-threshold",
      "0.50",
      "--protected-hard-negative-registry",
      item.protectedRegistry.registry,
      "--batch-date",
      "20260724",
      "--sequence-start",
      "161",
      "--sequence-end",
      "260",
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(wrongWeights.status, 0);
  assert.match(
    wrongWeights.stderr,
    /candidate weights do not match --expected-candidate-weights-sha256/,
  );

  const wrongThreshold = spawnSync(
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
      "--expected-candidate-weights-sha256",
      shaFile(item.weights),
      "--expected-score-threshold",
      "0.35",
      "--protected-hard-negative-registry",
      item.protectedRegistry.registry,
      "--batch-date",
      "20260724",
      "--sequence-start",
      "161",
      "--sequence-end",
      "260",
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(wrongThreshold.status, 0);
  assert.match(
    wrongThreshold.stderr,
    /candidate threshold does not match --expected-score-threshold/,
  );
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects normalized sourceIdentity overlap with protected training evidence", () => {
  const item = makeBatch();
  const protectedRegistry = makeProtectedRegistry(item.root, {
    sourceIdentityCollision: true,
  });
  const result = runRecorder(item, { registry: protectedRegistry.registry });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /sourceGroup overlaps a protected hard negative source/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
});

test("rejects dHash256 near overlap with protected training evidence", () => {
  const item = makeBatch();
  const candidate = path.join(
    item.images,
    "shard-a",
    "hard_negative_independent_20260724_161_fixture_family_01.png",
  );
  const protectedRegistry = makeProtectedRegistry(item.root, {
    perceptualCollisionImage: candidate,
  });
  const result = runRecorder(item, { registry: protectedRegistry.registry });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /perceptually duplicates a protected hard negative/);
  assert.equal(existsSync(path.join(item.images, freezeDirectory)), false);
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
