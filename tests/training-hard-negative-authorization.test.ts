import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
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
  createProtectedRoleEvidence,
  writePatternTestPng,
  writeTestPng,
} from "./helpers/hard-negative-evidence.ts";

const recorder = path.resolve(
  "model/training/record-training-hard-negative-authorization.py",
);
const builder = path.resolve(
  "model/training/build-independent-hard-negative-review-workspace.py",
);
const python = process.env.PYTHON ?? "python";

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

const canonicalSha = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function makeFixture(count = 3) {
  const root = mkdtempSync(path.join(tmpdir(), "training-hard-negative-auth-"));
  const sourceRoot = path.join(root, "images");
  const output = path.join(root, "evidence");
  const userAuthorization = path.join(root, "user-authorization.json");
  mkdirSync(sourceRoot);
  const relativePaths = Array.from({ length: count }, (_, index) => {
    const sequence = index + 1;
    const relative =
      `batch/hard_negative_training_20260726_` +
      `${String(sequence).padStart(3, "0")}_fixture_family_` +
      `${String(sequence).padStart(2, "0")}.png`;
    writePatternTestPng(path.join(sourceRoot, relative), sequence + 100, 768, 768);
    return relative;
  }).sort((left, right) => left.localeCompare(right));
  const confirmationNote =
    "用户明确允许这个精确文件集合用于商业模型训练与长期回归。";
  writeJson(userAuthorization, {
    schemaVersion: 1,
    ok: true,
    decision: "authorized_for_training_hard_negative_review",
    confirmedBy: "workspace-user",
    confirmationNote,
    authorizationEvidence: {
      kind: "codex-user-message",
      threadId: "019f4ca0-a894-7b63-8ec9-c286885a5a22",
      decisionId:
        "goal-thread/019f4ca0-a894-7b63-8ec9-c286885a5a22/training-authorization",
      userMessageText: confirmationNote,
      userMessageSha256: createHash("sha256")
        .update(confirmationNote)
        .digest("hex"),
    },
    sourceRoot,
    scopeIncludesDescendants: false,
    authorizedUses: [
      "commercial-model-training",
      "long-term-regression",
      "model-diagnostic-evaluation",
      "data-quality-review",
    ],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
    roleConstraint:
      "authorization-does-not-assign-train-validation-or-holdout-role",
    authorizedRelativePaths: relativePaths,
    authorizedRelativePathsSha256: canonicalSha(relativePaths),
  });
  // This unlisted image proves the recorder never infers authorization by
  // recursively scanning all images beneath sourceRoot.
  writePatternTestPng(
    path.join(
      sourceRoot,
      "unlisted",
      "hard_negative_training_20260726_099_unlisted_family_01.png",
    ),
    999,
    768,
    768,
  );
  const protectedRoot = path.join(root, "protected-hard-negatives");
  const createProtectedManifest = (
    label: string,
    decision:
      | "approved_hard_negative_manifest"
      | "approved_independent_hard_negative_holdout",
    trainingUse: "permitted" | "prohibited",
    fileName: string,
    sourceGroup: string,
    seed: number,
  ) => {
    const imagePath = path.join(protectedRoot, label, fileName);
    writePatternTestPng(imagePath, seed, 768, 768);
    const items = [
      {
        fileName,
        sourceFileName: fileName,
        sourceGroup,
        imageSha256: shaFile(imagePath),
        imagePath,
        width: 768,
        height: 768,
        imageFormat: "PNG",
        role:
          decision === "approved_hard_negative_manifest"
            ? "hard-negative"
            : "independent-holdout",
        originalResolutionVisualReview: true,
        trainingUse,
      },
    ];
    const manifest = path.join(root, `${label}.json`);
    writeJson(manifest, {
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision,
      trainingUse,
      itemsSha256: canonicalSha(items),
      items,
    });
    return manifest;
  };
  const protectedTraining = createProtectedManifest(
      "protected-training",
      "approved_hard_negative_manifest",
      "permitted",
      "hard_negative_independent_20260724_501_protected_train_01.png",
      "ai-hard-negative-training-2026-07-24:protected_train",
      8001,
    );
  const protectedHoldout = createProtectedManifest(
      "protected-holdout",
      "approved_independent_hard_negative_holdout",
      "prohibited",
      "hard_negative_independent_20260725_601_protected_holdout_01.png",
      "ai-hard-negative-independent-20260725:protected_holdout",
      8002,
    );
  const protectedTrainingDuplicate = path.join(
    root,
    "protected-training-duplicate.json",
  );
  writeFileSync(
    protectedTrainingDuplicate,
    readFileSync(protectedTraining),
  );
  const protectedHoldoutTwo = createProtectedManifest(
    "protected-holdout-two",
    "approved_independent_hard_negative_holdout",
    "prohibited",
    "nail_legacy_holdout_20260722_001.png",
    "ai-hard-negative-independent-20260722:legacy_holdout",
    8003,
  );
  const protectedManifests = [
    protectedTraining,
    protectedTrainingDuplicate,
    protectedHoldout,
    protectedHoldoutTwo,
  ];
  const protectedRegistry = path.join(root, "protected-registry.json");
  const registryEntries = protectedManifests
    .map((manifestPath) => {
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
      return {
        path: path.resolve(manifestPath),
        sha256: shaFile(manifestPath),
        role:
          manifest.decision === "approved_hard_negative_manifest"
            ? "training"
            : "holdout",
      };
    })
    .sort((left, right) => left.path.localeCompare(right.path));
  writeJson(protectedRegistry, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: registryEntries.length,
      trainingManifestCount: registryEntries.filter(
        (entry) => entry.role === "training",
      ).length,
      holdoutManifestCount: registryEntries.filter(
        (entry) => entry.role === "holdout",
      ).length,
    },
    entriesSha256: canonicalSha(registryEntries),
    entries: registryEntries,
  });
  return {
    root,
    sourceRoot,
    output,
    userAuthorization,
    relativePaths,
    protectedManifests,
    protectedRegistry,
  };
}

function runRecorder(item: ReturnType<typeof makeFixture>) {
  return spawnSync(
    python,
    [
      recorder,
      "--source-root",
      item.sourceRoot,
      "--user-authorization",
      item.userAuthorization,
      "--output-dir",
      item.output,
      "--protected-hard-negative-registry",
      item.protectedRegistry,
      "--batch-date",
      "20260726",
      "--sequence-start",
      "1",
      "--sequence-end",
      String(item.relativePaths.length),
    ],
    { encoding: "utf8" },
  );
}

function writeRegistryEntries(
  item: ReturnType<typeof makeFixture>,
  entries: Array<{ path: string; sha256: string; role: string }>,
) {
  writeJson(item.protectedRegistry, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: entries.length,
      trainingManifestCount: entries.filter(
        (entry) => entry.role === "training",
      ).length,
      holdoutManifestCount: entries.filter(
        (entry) => entry.role === "holdout",
      ).length,
    },
    entriesSha256: canonicalSha(entries),
    entries,
  });
}

function refreshRegistryHashes(item: ReturnType<typeof makeFixture>) {
  const registry = JSON.parse(readFileSync(item.protectedRegistry, "utf8"));
  const entries = registry.entries.map(
    (entry: { path: string; sha256: string; role: string }) => ({
      ...entry,
      sha256: shaFile(entry.path),
    }),
  );
  writeRegistryEntries(item, entries);
}

test("records an exact training batch and feeds the review workspace directly", () => {
  const item = makeFixture();
  const result = runRecorder(item);
  assert.equal(result.status, 0, result.stderr);

  const machinePath = path.join(item.output, "machine-audit-v1.json");
  const authorizationPath = path.join(
    item.output,
    "authorization-record-A-v1.json",
  );
  const machine = JSON.parse(readFileSync(machinePath, "utf8"));
  const authorization = JSON.parse(readFileSync(authorizationPath, "utf8"));
  assert.equal(machine.decodedCount, 3);
  assert.equal(machine.records.length, 3);
  assert.equal(machine.recordsSha256, canonicalSha(machine.records));
  assert.equal(machine.nearDuplicatePairs.length, 0);
  assert.equal(machine.protectedHardNegativeManifests.length, 4);
  assert.equal(machine.protectedHardNegativeRecords.length, 3);
  assert.equal(machine.protectedHardNegativeRegistry.manifestCount, 4);
  assert.equal(authorization.currentTrainingUse, "prohibited");
  assert.equal(authorization.entries.length, 3);
  assert.equal(authorization.entriesSha256, canonicalSha(authorization.entries));
  assert.ok(
    authorization.authorizedUses.includes("commercial-model-training"),
  );
  assert.ok(!authorization.authorizedUses.includes("independent-release-test"));
  assert.ok(
    authorization.entries.every(
      (entry: { fileName: string }) =>
        entry.fileName.startsWith("hard_negative_training_"),
    ),
  );

  const verified = spawnSync(
    python,
    [recorder, "--verify-authorization", authorizationPath],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);
  assert.equal(JSON.parse(verified.stdout).imageCount, 3);

  const protectedRoles = createProtectedRoleEvidence(item.root);
  const reviewOutput = path.join(item.root, "review");
  const built = spawnSync(
    python,
    [
      builder,
      "--authorization",
      authorizationPath,
      "--machine-audit",
      machinePath,
      "--train-index",
      protectedRoles.train,
      "--val-index",
      protectedRoles.val,
      "--frozen-test-manifest",
      protectedRoles.frozenTest,
      "--output-dir",
      reviewOutput,
    ],
    { encoding: "utf8" },
  );
  assert.equal(built.status, 0, built.stderr);
  const workspace = JSON.parse(
    readFileSync(path.join(reviewOutput, "review-workspace-v1.json"), "utf8"),
  );
  assert.equal(workspace.summary.authorizedImages, 3);
  assert.equal(
    workspace.inputs.authorization.deepReplay.mode,
    "training-authorization-deep-replay",
  );
  assert.equal(
    workspace.inputs.authorization.deepReplay.machineAuditSha256,
    shaFile(machinePath),
  );
  assert.ok(
    workspace.items.every((entry: { sourceGroup: string }) =>
      entry.sourceGroup.startsWith("ai-hard-negative-training-20260726:"),
    ),
  );
});

test("rejects mixed holdout authorization and an inexact source root", () => {
  const item = makeFixture();
  const authorization = JSON.parse(
    readFileSync(item.userAuthorization, "utf8"),
  );
  authorization.authorizedUses.push("independent-release-test");
  writeJson(item.userAuthorization, authorization);
  const mixed = runRecorder(item);
  assert.notEqual(mixed.status, 0);
  assert.match(mixed.stderr, /must exclude independent-release-test/);
  assert.equal(existsSync(item.output), false);

  authorization.authorizedUses = authorization.authorizedUses.filter(
    (value: string) => value !== "independent-release-test",
  );
  authorization.sourceRoot = item.root;
  writeJson(item.userAuthorization, authorization);
  const broad = runRecorder(item);
  assert.notEqual(broad.status, 0);
  assert.match(broad.stderr, /sourceRoot must exactly match/);
  assert.equal(existsSync(item.output), false);
});

test("requires both protected training and independent-holdout manifests", () => {
  for (const retainedRole of ["training", "holdout"]) {
    const item = makeFixture();
    const registry = JSON.parse(readFileSync(item.protectedRegistry, "utf8"));
    writeRegistryEntries(
      item,
      registry.entries.filter(
        (entry: { role: string }) => entry.role === retainedRole,
      ),
    );
    const result = runRecorder(item);
    assert.notEqual(result.status, 0);
    assert.match(
      result.stderr,
      /must include at least one approved training manifest and one approved independent holdout manifest/,
    );
  }
});

test("registry rejects omitted entries and manifest SHA-256 drift", () => {
  const item = makeFixture();
  const registry = JSON.parse(readFileSync(item.protectedRegistry, "utf8"));
  registry.entries.pop();
  writeJson(item.protectedRegistry, registry);
  const omitted = runRecorder(item);
  assert.notEqual(omitted.status, 0);
  assert.match(omitted.stderr, /registry contract is invalid/);

  const shaDrift = makeFixture();
  const driftedRegistry = JSON.parse(
    readFileSync(shaDrift.protectedRegistry, "utf8"),
  );
  driftedRegistry.entries[0].sha256 = "0".repeat(64);
  writeRegistryEntries(shaDrift, driftedRegistry.entries);
  const drifted = runRecorder(shaDrift);
  assert.notEqual(drifted.status, 0);
  assert.match(drifted.stderr, /registry manifest SHA-256 drift/);
});

test("accepts legacy protected names and binds every registry manifest", () => {
  const item = makeFixture();
  const verified = spawnSync(
    python,
    [recorder, "--verify-protected-registry", item.protectedRegistry],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);
  const result = JSON.parse(verified.stdout);
  assert.equal(result.manifestCount, 4);
  assert.equal(result.protectedRecordCount, 3);
});

test("rejects naming, sequence, and explicit-path escape violations", () => {
  const badName = makeFixture(2);
  const original = path.join(badName.sourceRoot, badName.relativePaths[1]);
  const invalidRelative = badName.relativePaths[1].replace(
    "hard_negative_training_",
    "hard_negative_independent_",
  );
  const invalid = path.join(badName.sourceRoot, invalidRelative);
  mkdirSync(path.dirname(invalid), { recursive: true });
  copyFileSync(original, invalid);
  const authorization = JSON.parse(
    readFileSync(badName.userAuthorization, "utf8"),
  );
  authorization.authorizedRelativePaths[1] = invalidRelative;
  authorization.authorizedRelativePaths.sort();
  authorization.authorizedRelativePathsSha256 = canonicalSha(
    authorization.authorizedRelativePaths,
  );
  writeJson(badName.userAuthorization, authorization);
  const badNameResult = runRecorder(badName);
  assert.notEqual(badNameResult.status, 0);
  assert.match(badNameResult.stderr, /does not match the training-batch contract/);
  assert.equal(existsSync(badName.output), false);

  const escaped = makeFixture(2);
  const escapedAuthorization = JSON.parse(
    readFileSync(escaped.userAuthorization, "utf8"),
  );
  escapedAuthorization.authorizedRelativePaths[0] =
    "../hard_negative_training_20260726_001_escape_family_01.png";
  escapedAuthorization.authorizedRelativePaths.sort();
  escapedAuthorization.authorizedRelativePathsSha256 = canonicalSha(
    escapedAuthorization.authorizedRelativePaths,
  );
  writeJson(escaped.userAuthorization, escapedAuthorization);
  const escapedResult = runRecorder(escaped);
  assert.notEqual(escapedResult.status, 0);
  assert.match(escapedResult.stderr, /not a safe relative path/);
  assert.equal(existsSync(escaped.output), false);

  const nonContiguous = makeFixture(2);
  const nonContiguousAuthorization = JSON.parse(
    readFileSync(nonContiguous.userAuthorization, "utf8"),
  );
  const secondRelative = nonContiguous.relativePaths[1];
  const thirdRelative = secondRelative
    .replace("_002_", "_003_")
    .replace("_02.png", "_03.png");
  copyFileSync(
    path.join(nonContiguous.sourceRoot, secondRelative),
    path.join(nonContiguous.sourceRoot, thirdRelative),
  );
  nonContiguousAuthorization.authorizedRelativePaths[1] = thirdRelative;
  nonContiguousAuthorization.authorizedRelativePaths.sort();
  nonContiguousAuthorization.authorizedRelativePathsSha256 = canonicalSha(
    nonContiguousAuthorization.authorizedRelativePaths,
  );
  writeJson(nonContiguous.userAuthorization, nonContiguousAuthorization);
  const nonContiguousResult = runRecorder(nonContiguous);
  assert.notEqual(nonContiguousResult.status, 0);
  assert.match(nonContiguousResult.stderr, /sequence is outside the explicit range/);
  assert.equal(existsSync(nonContiguous.output), false);
});

test("rejects exact and perceptual duplicates without leaving evidence", () => {
  const exact = makeFixture(2);
  copyFileSync(
    path.join(exact.sourceRoot, exact.relativePaths[0]),
    path.join(exact.sourceRoot, exact.relativePaths[1]),
  );
  const exactResult = runRecorder(exact);
  assert.notEqual(exactResult.status, 0);
  assert.match(exactResult.stderr, /duplicate image SHA-256/);
  assert.equal(existsSync(exact.output), false);

  const near = makeFixture(2);
  writeTestPng(path.join(near.sourceRoot, near.relativePaths[0]), 1, 768, 768);
  writeTestPng(path.join(near.sourceRoot, near.relativePaths[1]), 2, 768, 768);
  const nearResult = runRecorder(near);
  assert.notEqual(nearResult.status, 0);
  assert.match(nearResult.stderr, /perceptual near-duplicate gate failed/);
  assert.equal(existsSync(near.output), false);
});

test("rejects exact and perceptual duplicates against protected manifests", () => {
  const exact = makeFixture(1);
  const exactManifest = JSON.parse(
    readFileSync(exact.protectedManifests[0], "utf8"),
  );
  copyFileSync(
    exactManifest.items[0].imagePath,
    path.join(exact.sourceRoot, exact.relativePaths[0]),
  );
  const exactResult = runRecorder(exact);
  assert.notEqual(exactResult.status, 0);
  assert.match(exactResult.stderr, /exactly duplicates a protected hard negative/);
  assert.equal(existsSync(exact.output), false);

  const near = makeFixture(1);
  const protectedManifest = JSON.parse(
    readFileSync(near.protectedManifests[3], "utf8"),
  );
  writeTestPng(protectedManifest.items[0].imagePath, 1, 768, 768);
  protectedManifest.items[0].imageSha256 = shaFile(
    protectedManifest.items[0].imagePath,
  );
  protectedManifest.itemsSha256 = canonicalSha(protectedManifest.items);
  writeJson(near.protectedManifests[3], protectedManifest);
  refreshRegistryHashes(near);
  writeTestPng(path.join(near.sourceRoot, near.relativePaths[0]), 2, 768, 768);
  const nearResult = runRecorder(near);
  assert.notEqual(nearResult.status, 0);
  assert.match(
    nearResult.stderr,
    /perceptually duplicates a protected hard negative/,
  );
  assert.equal(existsSync(near.output), false);
});

test("enforces the fixed 768px minimum side", () => {
  const item = makeFixture(1);
  writePatternTestPng(
    path.join(item.sourceRoot, item.relativePaths[0]),
    77,
    767,
    1024,
  );
  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /minimum side is below 768px/);
  assert.equal(existsSync(item.output), false);
});

test("rejects linked path components", (t) => {
  const item = makeFixture(1);
  const authorization = JSON.parse(
    readFileSync(item.userAuthorization, "utf8"),
  );
  const outside = path.join(item.root, "outside");
  const linked = path.join(item.sourceRoot, "linked");
  mkdirSync(outside);
  const fileName =
    "hard_negative_training_20260726_001_linked_family_01.png";
  writePatternTestPng(path.join(outside, fileName), 778, 768, 768);
  try {
    symlinkSync(
      outside,
      linked,
      process.platform === "win32" ? "junction" : "dir",
    );
  } catch (error) {
    t.skip(`link creation is unavailable in this environment: ${String(error)}`);
    return;
  }
  authorization.authorizedRelativePaths = [`linked/${fileName}`];
  authorization.authorizedRelativePathsSha256 = canonicalSha(
    authorization.authorizedRelativePaths,
  );
  writeJson(item.userAuthorization, authorization);
  const result = runRecorder(item);
  assert.notEqual(result.status, 0);
  assert.match(
    result.stderr,
    /symbolic link, junction, or reparse-point entry is prohibited/,
  );
  assert.equal(existsSync(item.output), false);

  const rootItem = makeFixture(1);
  const linkedRoot = path.join(rootItem.root, "linked-root");
  try {
    symlinkSync(
      rootItem.sourceRoot,
      linkedRoot,
      process.platform === "win32" ? "junction" : "dir",
    );
  } catch (error) {
    t.diagnostic(
      `root-link creation is unavailable in this environment: ${String(error)}`,
    );
    return;
  }
  const rootAuthorization = JSON.parse(
    readFileSync(rootItem.userAuthorization, "utf8"),
  );
  rootAuthorization.sourceRoot = linkedRoot;
  writeJson(rootItem.userAuthorization, rootAuthorization);
  const linkedRootResult = runRecorder({
    ...rootItem,
    sourceRoot: linkedRoot,
  });
  assert.notEqual(linkedRootResult.status, 0);
  assert.match(
    linkedRootResult.stderr,
    /source root cannot traverse a symbolic link, junction, or reparse point/,
  );
  assert.equal(existsSync(rootItem.output), false);
});

test("detects authorization drift and refuses output overwrite", () => {
  const item = makeFixture();
  const first = runRecorder(item);
  assert.equal(first.status, 0, first.stderr);
  const authorizationPath = path.join(
    item.output,
    "authorization-record-A-v1.json",
  );
  const machinePath = path.join(item.output, "machine-audit-v1.json");
  const authorizationHash = shaFile(authorizationPath);
  const machineHash = shaFile(machinePath);

  const repeated = runRecorder(item);
  assert.notEqual(repeated.status, 0);
  assert.match(repeated.stderr, /refusing to overwrite existing evidence directory/);
  assert.equal(shaFile(authorizationPath), authorizationHash);
  assert.equal(shaFile(machinePath), machineHash);

  const protectedManifestPath = item.protectedManifests[0];
  const protectedManifestBytes = readFileSync(protectedManifestPath);
  const protectedManifest = JSON.parse(protectedManifestBytes.toString("utf8"));
  protectedManifest.auditNote = "drift";
  writeJson(protectedManifestPath, protectedManifest);
  const protectedVerified = spawnSync(
    python,
    [recorder, "--verify-authorization", authorizationPath],
    { encoding: "utf8" },
  );
  assert.notEqual(protectedVerified.status, 0);
  assert.match(
    protectedVerified.stderr,
    /protected registry manifest SHA-256 drift/,
  );
  writeFileSync(protectedManifestPath, protectedManifestBytes);

  const source = JSON.parse(readFileSync(item.userAuthorization, "utf8"));
  source.confirmationNote = `${source.confirmationNote} 已修改`;
  writeJson(item.userAuthorization, source);
  const verified = spawnSync(
    python,
    [recorder, "--verify-authorization", authorizationPath],
    { encoding: "utf8" },
  );
  assert.notEqual(verified.status, 0);
  assert.match(verified.stderr, /user authorization source SHA-256 drift/);
});
