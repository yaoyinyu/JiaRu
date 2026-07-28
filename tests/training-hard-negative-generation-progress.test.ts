import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { deflateSync } from "node:zlib";

const auditor = path.resolve(
  "model/training/audit-training-hard-negative-generation-progress.py",
);
const authorizationBuilder = path.resolve(
  "model/training/build-training-hard-negative-user-authorization.py",
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

let crcTable: Uint32Array | undefined;
function crc32(data: Buffer) {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let index = 0; index < 256; index++) {
      let value = index;
      for (let bit = 0; bit < 8; bit++) {
        value = (value & 1) !== 0 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      }
      crcTable[index] = value >>> 0;
    }
  }
  let value = 0xffffffff;
  for (const byte of data) value = crcTable[(value ^ byte) & 0xff] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, payload: Buffer) {
  const name = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(payload.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([name, payload])));
  return Buffer.concat([length, name, payload, checksum]);
}

function writeGridPng(
  file: string,
  seed: number,
  width = 768,
  height = 768,
  tag = "",
) {
  mkdirSync(path.dirname(file), { recursive: true });
  const raw = Buffer.alloc((width + 1) * height);
  const rows = 16;
  const columns = 17;
  const mix = (x: number, y: number) => {
    let value =
      (Math.imul(seed + 101, 0x9e3779b1) ^
        Math.imul(x + 17, 0x85ebca6b) ^
        Math.imul(y + 31, 0xc2b2ae35)) >>>
      0;
    value ^= value >>> 16;
    value = Math.imul(value, 0x7feb352d) >>> 0;
    value ^= value >>> 15;
    return (value ^ (value >>> 16)) & 0xff;
  };
  for (let y = 0; y < height; y++) {
    const offset = y * (width + 1);
    raw[offset] = 0;
    const cellY = Math.min(rows - 1, Math.floor((y * rows) / height));
    for (let x = 0; x < width; x++) {
      const cellX = Math.min(columns - 1, Math.floor((x * columns) / width));
      raw[offset + 1 + x] = mix(cellX, cellY);
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 0;
  const chunks = [
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(raw, { level: 1 })),
  ];
  if (tag) chunks.push(pngChunk("tEXt", Buffer.from(`fixture\0${tag}`, "latin1")));
  chunks.push(pngChunk("IEND", Buffer.alloc(0)));
  writeFileSync(file, Buffer.concat(chunks));
}

type Fixture = ReturnType<typeof makeFixture>;

function makeFixture() {
  const root = mkdtempSync(path.join(tmpdir(), "hard-negative-generation-progress-"));
  const sourceRoot = path.join(root, "candidate-pool");
  const protectedRoot = path.join(root, "protected");
  mkdirSync(sourceRoot);

  const createProtectedManifest = (
    role: "training" | "holdout",
    seed: number,
  ) => {
    const decision =
      role === "training"
        ? "approved_hard_negative_manifest"
        : "approved_independent_hard_negative_holdout";
    const trainingUse = role === "training" ? "permitted" : "prohibited";
    const fileName = `hard_negative_independent_20260720_${role === "training" ? "401" : "501"}_protected_${role}_01.png`;
    const imagePath = path.join(protectedRoot, role, fileName);
    writeGridPng(imagePath, seed);
    const items = [
      {
        fileName,
        sourceFileName: fileName,
        sourceGroup: `ai-hard-negative-${role}-20260720:protected_${role}`,
        imageSha256: shaFile(imagePath),
        imagePath,
        width: 768,
        height: 768,
        imageFormat: "PNG",
        role: role === "training" ? "hard-negative" : "independent-holdout",
        originalResolutionVisualReview: true,
        trainingUse,
      },
    ];
    const manifestPath = path.join(root, `protected-${role}.json`);
    writeJson(manifestPath, {
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision,
      trainingUse,
      itemsSha256: canonicalSha(items),
      items,
    });
    return { manifestPath, imagePath };
  };
  const protectedTraining = createProtectedManifest("training", 9001);
  const protectedHoldout = createProtectedManifest("holdout", 9002);
  const registryEntries = [
    {
      path: path.resolve(protectedTraining.manifestPath),
      sha256: shaFile(protectedTraining.manifestPath),
      role: "training",
    },
    {
      path: path.resolve(protectedHoldout.manifestPath),
      sha256: shaFile(protectedHoldout.manifestPath),
      role: "holdout",
    },
  ].sort((left, right) => left.path.localeCompare(right.path));
  const registry = path.join(root, "protected-registry.json");
  writeJson(registry, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: 2,
      trainingManifestCount: 1,
      holdoutManifestCount: 1,
    },
    entriesSha256: canonicalSha(registryEntries),
    entries: registryEntries,
  });

  const planItems = Array.from({ length: 160 }, (_, index) => {
    const sequence = index + 1;
    const familyNumber = Math.floor(index / 10) + 1;
    const variant = (index % 10) + 1;
    const family = `family_${String(familyNumber).padStart(2, "0")}`;
    return {
      sequence,
      expectedFileName:
        `hard_negative_training_20260726_${String(sequence).padStart(3, "0")}_` +
        `${family}_${String(variant).padStart(2, "0")}.png`,
      promptId: `prompt.${String(sequence).padStart(3, "0")}`,
      promptFamily: family,
      promptVariant: variant,
      role: "training-candidate",
      trainingUse: "prohibited",
    };
  });
  const plan = path.join(root, "generation-plan.json");
  writeJson(plan, {
    schemaVersion: 1,
    ok: true,
    decision: "training_hard_negative_generation_plan",
    role: "training-candidate",
    trainingUse: "prohibited",
    authorizationStatus: "missing",
    sourceRoot: path.resolve(sourceRoot),
    batchDate: "20260726",
    expectedCount: 160,
    minimumSide: 768,
    nearDuplicateThreshold: 12,
    protectedHardNegativeRegistry: {
      path: path.resolve(registry),
      sha256: shaFile(registry),
    },
    itemsSha256: canonicalSha(planItems),
    items: planItems,
  });
  return {
    root,
    sourceRoot,
    registry,
    plan,
    planItems,
    protectedTrainingImage: protectedTraining.imagePath,
  };
}

function imagePath(item: Fixture, sequence: number) {
  return path.join(item.sourceRoot, item.planItems[sequence - 1].expectedFileName);
}

function addImage(
  item: Fixture,
  sequence: number,
  seed = sequence,
  width = 768,
  height = 768,
  tag = "",
) {
  writeGridPng(imagePath(item, sequence), seed, width, height, tag);
}

function runAudit(item: Fixture, output: string, previous?: string) {
  const args = [
    auditor,
    "--source-root",
    item.sourceRoot,
    "--plan",
    item.plan,
    "--protected-hard-negative-registry",
    item.registry,
    "--output",
    output,
  ];
  if (previous) args.push("--previous-report", previous);
  return spawnSync(python, args, { encoding: "utf8" });
}

test("partial pool produces a truthful HOLD with next missing and family counts", () => {
  const item = makeFixture();
  addImage(item, 1, 101);
  addImage(item, 2, 102);
  const output = path.join(item.root, "partial-report.json");
  const result = runAudit(item, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.status, "HOLD");
  assert.equal(report.decision, "hold_generation_incomplete_or_machine_gate_failed");
  assert.deepEqual(report.summary, {
    expected: 160,
    present: 2,
    missing: 158,
    passed: 2,
    failed: 0,
    unknown: 0,
  });
  assert.equal(report.nextMissing.sequence, 3);
  assert.deepEqual(report.familyCounts.family_01, {
    expected: 10,
    present: 2,
    missing: 8,
    passed: 2,
    failed: 0,
  });
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.authorizationStatus, "missing");
  assert.equal(report.itemsCurrentSha256, canonicalSha(report.items));
});

test("a machine-clean 160-item pool only becomes ready to request authorization", () => {
  const item = makeFixture();
  for (let sequence = 1; sequence <= 160; sequence++) {
    addImage(item, sequence, sequence + 2000);
  }
  const output = path.join(item.root, "complete-report.json");
  const result = runAudit(item, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.status, "READY");
  assert.equal(report.decision, "ready_to_request_exact_user_authorization");
  assert.equal(report.summary.present, 160);
  assert.equal(report.summary.passed, 160);
  assert.equal(report.summary.missing, 0);
  assert.equal(report.summary.failed, 0);
  assert.equal(report.nextMissing, null);
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.authorizationStatus, "missing");

  const requiredConfirmationText =
    "允许将 candidate3-training-v1 最终冻结的精确文件清单用于商业模型训练和长期回归；不用于独立发布测试；授权不放宽质量门。";
  const requestedItems = report.items.map(
    (entry: {
      sequence: number;
      expectedFileName: string;
      sha256: string;
      dhash256: string;
      width: number;
      height: number;
      promptId: string;
      promptFamily: string;
      promptVariant: number;
    }) => ({
      sequence: entry.sequence,
      relativePath: entry.expectedFileName,
      sha256: entry.sha256,
      dhash256: entry.dhash256,
      width: entry.width,
      height: entry.height,
      promptId: entry.promptId,
      promptFamily: entry.promptFamily,
      promptVariant: entry.promptVariant,
    }),
  );
  const request = path.join(item.root, "exact-authorization-request.json");
  writeJson(request, {
    schemaVersion: 1,
    ok: false,
    status: "HOLD",
    decision: "awaiting_exact_user_confirmation",
    role: "training-hard-negative-candidate",
    trainingUse: "prohibited",
    authorizationStatus: "pending-user-confirmation",
    sourceRoot: path.resolve(item.sourceRoot),
    scopeIncludesDescendants: false,
    inputs: {
      generationProgressReport: {
        path: path.resolve(output),
        sha256: shaFile(output),
      },
      generationPlan: report.inputs.generationPlan,
      protectedHardNegativeRegistry:
        report.inputs.protectedHardNegativeRegistry,
      itemsCurrentSha256: report.itemsCurrentSha256,
    },
    summary: {
      requestedFileCount: 160,
      machinePassed: 160,
      originalResolutionVisualReviewApproved: 0,
      trainingApproved: 0,
    },
    requestedUses: [
      "commercial-model-training",
      "long-term-regression",
      "model-diagnostic-evaluation",
      "data-quality-review",
    ],
    excludedUses: ["independent-release-test"],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
    roleConstraint:
      "authorization-does-not-assign-train-validation-or-holdout-role",
    requiredConfirmationText,
    requestedRelativePaths: requestedItems.map(
      (entry: { relativePath: string }) => entry.relativePath,
    ),
    requestedItems,
  });
  const authorization = path.join(item.root, "user-authorization.json");
  const threadId = "019f4ca0-a894-7b63-8ec9-c286885a5a22";
  const creation = spawnSync(
    python,
    [
      authorizationBuilder,
      "--authorization-request",
      request,
      "--user-message",
      requiredConfirmationText,
      "--thread-id",
      threadId,
      "--decision-id",
      `goal-thread/${threadId}/training-authorization/2026-07-28`,
      "--output",
      authorization,
    ],
    { encoding: "utf8" },
  );
  assert.equal(creation.status, 0, creation.stderr);
  const authorizationRecord = JSON.parse(readFileSync(authorization, "utf8"));
  assert.equal(authorizationRecord.ok, true);
  assert.equal(authorizationRecord.currentTrainingUse, "prohibited");
  assert.equal(authorizationRecord.authorizedRelativePaths.length, 160);
  assert.equal(
    authorizationRecord.authorizedRelativePathsSha256,
    canonicalSha(authorizationRecord.authorizedRelativePaths),
  );
  assert.equal(
    authorizationRecord.authorizationEvidence.userMessageSha256,
    createHash("sha256").update(requiredConfirmationText).digest("hex"),
  );
  const verification = spawnSync(
    python,
    [authorizationBuilder, "--verify-authorization", authorization],
    { encoding: "utf8" },
  );
  assert.equal(verification.status, 0, verification.stderr);

  const overwrite = spawnSync(
    python,
    [
      authorizationBuilder,
      "--authorization-request",
      request,
      "--user-message",
      requiredConfirmationText,
      "--thread-id",
      threadId,
      "--decision-id",
      `goal-thread/${threadId}/training-authorization/2026-07-28`,
      "--output",
      authorization,
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(overwrite.status, 0);
  assert.match(overwrite.stderr, /refusing to overwrite existing output/);
});

test("previous report permits growth but rejects a completed image hash drift", () => {
  const item = makeFixture();
  addImage(item, 1, 3101);
  const first = path.join(item.root, "progress-001.json");
  assert.equal(runAudit(item, first).status, 0);

  addImage(item, 2, 3102);
  const second = path.join(item.root, "progress-002.json");
  const growth = runAudit(item, second, first);
  assert.equal(growth.status, 0, growth.stderr);
  const report = JSON.parse(readFileSync(second, "utf8"));
  assert.equal(report.summary.present, 2);
  assert.equal(report.inputs.previousReport.sha256, shaFile(first));

  addImage(item, 1, 9999);
  const drifted = runAudit(item, path.join(item.root, "progress-003.json"), second);
  assert.notEqual(drifted.status, 0);
  assert.match(drifted.stderr, /previously completed image SHA-256 drift/);
});

test("unknown, corrupt, low-resolution, exact, and perceptual duplicates remain HOLD", () => {
  const item = makeFixture();
  addImage(item, 1, 4101);
  writeFileSync(imagePath(item, 2), Buffer.from("not an image"));
  addImage(item, 3, 4103, 767, 768);
  addImage(item, 4, 4104);
  copyFileSync(imagePath(item, 4), imagePath(item, 5));
  addImage(item, 6, 4106, 768, 768, "left");
  addImage(item, 7, 4106, 768, 768, "right");
  writeFileSync(path.join(item.sourceRoot, "unexpected.txt"), "unexpected");
  const output = path.join(item.root, "failed-report.json");
  const result = runAudit(item, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.status, "HOLD");
  assert.ok(report.summary.failed >= 7);
  const codes = new Set(report.issues.map((issue: { code: string }) => issue.code));
  assert.ok(codes.has("UNKNOWN_SOURCE_ENTRY"));
  assert.ok(codes.has("IMAGE_MACHINE_GATE_FAILED"));
  assert.ok(codes.has("BATCH_EXACT_DUPLICATE"));
  assert.ok(codes.has("BATCH_PERCEPTUAL_NEAR_DUPLICATE"));
  assert.equal(report.unknownFiles[0].name, "unexpected.txt");
});

test("protected registry exact overlap is rejected without granting training use", () => {
  const item = makeFixture();
  copyFileSync(item.protectedTrainingImage, imagePath(item, 1));
  const output = path.join(item.root, "protected-overlap-report.json");
  const result = runAudit(item, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.status, "HOLD");
  assert.ok(
    report.issues.some(
      (issue: { code: string }) => issue.code === "PROTECTED_EXACT_DUPLICATE",
    ),
  );
  assert.equal(report.items[0].state, "failed");
  assert.equal(report.trainingUse, "prohibited");
});

test("output is non-overwriting and report verification deeply replays the pool", () => {
  const item = makeFixture();
  addImage(item, 1, 6101);
  const output = path.join(item.root, "report.json");
  const created = runAudit(item, output);
  assert.equal(created.status, 0, created.stderr);

  const overwrite = runAudit(item, output);
  assert.notEqual(overwrite.status, 0);
  assert.match(overwrite.stderr, /refusing to overwrite existing output/);

  const insidePool = runAudit(item, path.join(item.sourceRoot, "report.json"));
  assert.notEqual(insidePool.status, 0);
  assert.match(insidePool.stderr, /output cannot be placed inside/);

  const verified = spawnSync(
    python,
    [auditor, "--verify-report", output],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);
  assert.equal(JSON.parse(verified.stdout).summary.present, 1);

  addImage(item, 2, 6102);
  const stale = spawnSync(
    python,
    [auditor, "--verify-report", output],
    { encoding: "utf8" },
  );
  assert.notEqual(stale.status, 0);
  assert.match(stale.stderr, /deep replay drift/);
});
