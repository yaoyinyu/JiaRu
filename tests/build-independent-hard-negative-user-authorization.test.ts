import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const python = process.env.PYTHON ?? "python";
const builder = path.resolve(
  "model/training/build-independent-hard-negative-user-authorization.py",
);
const recorder = path.resolve(
  "model/training/record-independent-hard-negative-authorization.py",
);

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

function writeJson(file: string, value: unknown) {
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function makeEvidence() {
  const root = mkdtempSync(path.join(tmpdir(), "independent-exact-auth-"));
  const images = path.join(root, "images");
  mkdirSync(images, { recursive: true });
  const weights = path.join(root, "candidate.pt");
  const threshold = path.join(root, "threshold.json");
  const registry = path.join(root, "protected-registry.json");
  writeFileSync(weights, "candidate-weights-fixture");
  writeFileSync(threshold, "threshold-evidence-fixture");
  writeFileSync(registry, "protected-registry-fixture");

  const candidates: Record<string, unknown>[] = [];
  const records: Record<string, unknown>[] = [];
  for (let index = 0; index < 100; index++) {
    const sequence = 261 + index;
    const batchLetter = String.fromCharCode(97 + Math.floor(index / 10));
    const variant = (index % 10) + 1;
    const batch = `batch-${batchLetter}`;
    const family = `batch_${batchLetter}`;
    const fileName =
      `hard_negative_independent_20260728_${sequence}_${family}_` +
      `${String(variant).padStart(2, "0")}.png`;
    const relativePath = `${batch}/${fileName}`;
    const sourcePath = path.join(images, batch, fileName);
    mkdirSync(path.dirname(sourcePath), { recursive: true });
    writeFileSync(sourcePath, `exact-authorized-image-${sequence}`);
    const sha256 = shaFile(sourcePath);
    const bytes = readFileSync(sourcePath).byteLength;
    candidates.push({
      sequence,
      batch,
      fileName,
      relativePath,
      sourcePath,
      bytes,
      sha256,
      generatedBy: "built-in-imagegen",
      modelInferenceBeforeFreeze: false,
      originalResolutionVisualReview: "pass-candidate-only",
    });
    records.push({
      fileName,
      relativePath,
      sourcePath,
      sha256,
      width: 1024,
      height: 1536,
      format: "PNG",
      bytes,
      dhash256: sequence.toString(16).padStart(64, "0"),
      sequence,
      batchDate: "20260728",
      promptFamily: family,
      promptVariant: variant,
      sourceGroup: `ai-hard-negative-independent-20260728:${family}`,
      sourceIdentity: `ai-hard-negative-20260728:${family}`,
    });
  }

  const candidateList = path.join(root, "candidate-list.json");
  const preaudit = path.join(root, "preaudit.json");
  writeJson(candidateList, {
    schemaVersion: 1,
    decision:
      "generated_independent_holdout_candidate_list_ready_for_exact_user_authorization",
    sourceRoot: images,
    sequenceStart: 261,
    sequenceEnd: 360,
    count: 100,
    trainingUse: "prohibited",
    evaluationUse: "prohibited-until-exact-user-authorization-and-atomic-freeze",
    qualityGateRelaxed: false,
    candidateModelInferencePerformed: false,
    items: candidates,
  });
  writeJson(preaudit, {
    schemaVersion: 1,
    ok: true,
    decision: "pre_authorization_machine_audit_pass_candidate_only",
    sourceRoot: images,
    sequenceStart: 261,
    sequenceEnd: 360,
    fileCount: 100,
    decodedCount: 100,
    trainingUse: "prohibited",
    evaluationUse: "prohibited-until-exact-user-authorization-and-atomic-freeze",
    candidateModelInferencePerformed: false,
    nearDuplicateThreshold: 12,
    nearDuplicatePairs: [],
    protectedCrossCheck: {
      decision: "pass_no_protected_hard_negative_overlap",
      candidateRecordCount: 100,
      protectedRecordCount: 2,
      exactSha256Matches: 0,
      sourceIdentityMatches: 0,
      perceptualMatchesAtOrBelowThreshold: 0,
      perceptualComparisons: 200,
      nearDuplicateThreshold: 12,
    },
    thresholdVerification: {
      path: threshold,
      sha256: shaFile(threshold),
      scoreThreshold: 0.35,
      weightsSha256: shaFile(weights),
      decision: "calibrated_threshold_ready_for_candidate_manifest",
    },
    candidateWeights: weights,
    candidateWeightsSha256: shaFile(weights),
    protectedRegistry: registry,
    protectedRegistrySha256: shaFile(registry),
    recordsSha256: canonicalSha(records),
    records,
  });
  return { root, images, candidateList, preaudit, records };
}

test("builds and deeply verifies an exact 100-file independent holdout authorization", (t) => {
  const item = makeEvidence();
  t.after(() => rmSync(item.root, { recursive: true, force: true }));
  const inspected = spawnSync(
    python,
    [
      builder,
      "--candidate-list",
      item.candidateList,
      "--preauthorization-audit",
      item.preaudit,
      "--inspect",
    ],
    { encoding: "utf8" },
  );
  assert.equal(inspected.status, 0, inspected.stderr);
  const inspection = JSON.parse(inspected.stdout);
  assert.equal(inspection.decision, "ready_for_exact_user_authorization");
  assert.equal(inspection.imageCount, 100);
  assert.equal(inspection.authorizedItemsSha256, canonicalSha(item.records));

  const output = path.join(item.root, "authorization-v2.json");
  const threadId = "019f4ca0-a894-7b63-8ec9-c286885a5a22";
  const created = spawnSync(
    python,
    [
      builder,
      "--candidate-list",
      item.candidateList,
      "--preauthorization-audit",
      item.preaudit,
      "--user-message",
      inspection.requiredConfirmationText,
      "--thread-id",
      threadId,
      "--decision-id",
      `goal-thread/${threadId}/exact-independent-holdout-authorization`,
      "--output",
      output,
    ],
    { encoding: "utf8" },
  );
  assert.equal(created.status, 0, created.stderr);
  const authorization = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(authorization.schemaVersion, 2);
  assert.equal(authorization.authorizedItems.length, 100);
  assert.equal(authorization.authorizedItemsSha256, canonicalSha(item.records));
  assert.deepEqual(authorization.excludedUses, ["commercial-model-training"]);
  assert.equal(authorization.currentTrainingUse, "prohibited");

  const verified = spawnSync(
    python,
    [builder, "--verify-authorization", output],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);
  assert.equal(
    JSON.parse(verified.stdout).decision,
    "exact_independent_holdout_authorization_verified",
  );

  const code = [
    "import importlib.util,json,sys",
    "spec=importlib.util.spec_from_file_location('recorder',sys.argv[1])",
    "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)",
    "authorization=json.load(open(sys.argv[2],encoding='utf-8'))",
    "records=authorization['authorizedItems']",
    "records[0]=dict(records[0],sha256='0'*64)",
    "module.validate_exact_authorized_items(authorization,records,'20260728',261,360)",
  ].join(";");
  const drifted = spawnSync(python, ["-c", code, recorder, output], {
    encoding: "utf8",
  });
  assert.notEqual(drifted.status, 0);
  assert.match(drifted.stderr, /differs from the exact file list/);
});

test("rejects non-exact confirmation and post-authorization image drift", (t) => {
  const item = makeEvidence();
  t.after(() => rmSync(item.root, { recursive: true, force: true }));
  const inspection = JSON.parse(
    spawnSync(
      python,
      [
        builder,
        "--candidate-list",
        item.candidateList,
        "--preauthorization-audit",
        item.preaudit,
        "--inspect",
      ],
      { encoding: "utf8" },
    ).stdout,
  );
  const threadId = "019f4ca0-a894-7b63-8ec9-c286885a5a22";
  const wrongOutput = path.join(item.root, "wrong.json");
  const wrong = spawnSync(
    python,
    [
      builder,
      "--candidate-list",
      item.candidateList,
      "--preauthorization-audit",
      item.preaudit,
      "--user-message",
      `${inspection.requiredConfirmationText}额外放宽`,
      "--thread-id",
      threadId,
      "--decision-id",
      `goal-thread/${threadId}/wrong`,
      "--output",
      wrongOutput,
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(wrong.status, 0);
  assert.equal(existsSync(wrongOutput), false);

  const output = path.join(item.root, "authorization-v2.json");
  const created = spawnSync(
    python,
    [
      builder,
      "--candidate-list",
      item.candidateList,
      "--preauthorization-audit",
      item.preaudit,
      "--user-message",
      inspection.requiredConfirmationText,
      "--thread-id",
      threadId,
      "--decision-id",
      `goal-thread/${threadId}/valid`,
      "--output",
      output,
    ],
    { encoding: "utf8" },
  );
  assert.equal(created.status, 0, created.stderr);
  writeFileSync(
    path.join(item.images, item.records[0].relativePath as string),
    "changed-after-user-authorization",
  );
  const verified = spawnSync(
    python,
    [builder, "--verify-authorization", output],
    { encoding: "utf8" },
  );
  assert.notEqual(verified.status, 0);
  assert.match(verified.stderr, /identity drift/);
});
