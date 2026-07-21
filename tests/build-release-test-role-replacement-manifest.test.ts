import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const python = process.platform === "win32" ? "python" : "python3";
const script = path.resolve(
  "model/training/build-release-test-role-replacement-manifest.py",
);

const hashBytes = (value: string) =>
  createHash("sha256").update(value).digest("hex");
const hashFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");
const canonicalHash = (value: unknown) => {
  const normalize = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(normalize);
    if (item && typeof item === "object") {
      return Object.fromEntries(
        Object.entries(item)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([key, child]) => [key, normalize(child)]),
      );
    }
    return item;
  };
  return createHash("sha256").update(JSON.stringify(normalize(value))).digest("hex");
};
const writeJson = (file: string, value: unknown) =>
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);

type Fixture = {
  root: string;
  imageRoot: string;
  plan: string;
  authorization: string;
  screening: string;
  trainingTruth: string;
  validationTruth: string;
  frozen: string;
  reviews: string;
  output: string;
};

function truthItems(prefix: string, count: number) {
  return Array.from({ length: count }, (_, index) => {
    const number = String(index + 1).padStart(3, "0");
    return {
      fileName: `${prefix}-${number}.jpg`,
      imageSha256: hashBytes(`${prefix}-truth-${number}`),
      sourceGroup: `${prefix}-group-${number}`,
      completeMaskCount: 5,
    };
  });
}

function fixture(): Fixture {
  const root = mkdtempSync(path.join(tmpdir(), "release-role-replacement-"));
  const imageRoot = path.join(root, "images");
  mkdirSync(imageRoot);

  const originalItems = Array.from({ length: 33 }, (_, index) => {
    const number = String(index + 1).padStart(2, "0");
    const fileName = `original-${number}.jpg`;
    const bytes = `original-image-${number}`;
    writeFileSync(path.join(imageRoot, fileName), bytes);
    return {
      fileName,
      sha256: hashBytes(bytes),
      sourceGroup: `original-group-${number}`,
      assignedRole: "independent-release-test",
      firstAnnotationBatch: false,
      fullyVisibleNails: 5,
      trainingUse: "prohibited",
      annotationTruthStatus: "not-started",
    };
  });
  const replacements = [1, 2].map((index) => {
    const fileName = `replacement-${index}.jpg`;
    const bytes = `replacement-image-${index}`;
    writeFileSync(path.join(imageRoot, fileName), bytes);
    return {
      fileName,
      sha256: hashBytes(bytes),
      sourceGroup: "replacement-complete-group",
      assignedRole: "train",
      firstAnnotationBatch: false,
      fullyVisibleNails: index === 1 ? 5 : 4,
      trainingUse: "prohibited",
      annotationTruthStatus: "not-started",
    };
  });
  const planItems = [...originalItems, ...replacements];

  const authorization = path.join(root, "authorization.json");
  const authorizationEntries = planItems.map((item) => ({
    fileName: item.fileName,
    sha256: item.sha256,
    sourceGroup: item.sourceGroup,
    trainingUse: "prohibited",
    authorizedUses: [
      "commercial-model-training",
      "independent-release-test",
      "long-term-regression",
    ],
  }));
  writeJson(authorization, {
    ok: true,
    root: imageRoot,
    authorization: {
      status: "confirmed",
      decision: "A",
      authorizedUses: [
        "commercial-model-training",
        "independent-release-test",
        "long-term-regression",
      ],
    },
    entriesSha256: canonicalHash(authorizationEntries),
    entries: authorizationEntries,
  });

  const screening = path.join(root, "screening.json");
  writeJson(screening, {
    ok: true,
    decision: "source_screening_batch_pass",
    items: planItems.map((item) => ({
      fileName: item.fileName,
      sha256: item.sha256,
      sourceGroup: item.sourceGroup,
      decision: "keep-for-annotation",
      fullyVisibleNails: item.fullyVisibleNails,
      trainingUse: "prohibited",
      annotationTruthStatus: "not-started",
    })),
  });

  const plan = path.join(root, "plan.json");
  writeJson(plan, {
    ok: true,
    decision: "first_annotation_batch_plan_ready_mask_review_required",
    inputs: {
      authorizationSha256: hashFile(authorization),
      screeningBatchSha256: hashFile(screening),
    },
    policy: { sourceGroupAtomicAcrossRoles: true },
    items: planItems,
  });

  const trainingTruth = path.join(root, "training-truth.json");
  const trainingItems = truthItems("train", 100);
  writeJson(trainingTruth, {
    ok: true,
    decision: "approved_unique_training_truth_index",
    summary: { uniqueImageCount: 100, conflictingImageCount: 0 },
    canonicalTruths: trainingItems,
  });
  const validationTruth = path.join(root, "validation-truth.json");
  const validationItems = truthItems("val", 30);
  writeJson(validationTruth, {
    ok: true,
    decision: "approved_unique_validation_truth_index",
    summary: { uniqueImageCount: 30, conflictingImageCount: 0 },
    canonicalTruths: validationItems,
  });

  const frozen = path.join(root, "frozen.json");
  const frozenItems = truthItems("frozen", 67).map((item) => ({
    ...item,
    parentFileName: item.fileName,
    parentSourceGroup: item.sourceGroup,
    trainingUse: "prohibited",
  }));
  writeJson(frozen, {
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: 67 },
    itemsSha256: canonicalHash(frozenItems),
    items: frozenItems,
  });

  const reviews = path.join(root, "reviews.json");
  writeJson(reviews, {
    ok: true,
    decision: "reviewed_release_test_role_replacements",
    policy: {
      originalResolutionReviewCompleted: true,
      completeVisibleNailSurfaceRequired: true,
      sourceGroupAtomicReplacementRequired: true,
    },
    items: [
      ...originalItems.map((item, index) => ({
        fileName: item.fileName,
        sha256: item.sha256,
        sourceGroup: item.sourceGroup,
        fullyVisibleNails: item.fullyVisibleNails,
        decision: index >= 31 ? "exclude" : "keep",
        originalResolutionReviewed: true,
        reason: index >= 31 ? "required nail is incomplete" : "all visible nails are complete",
      })),
      ...replacements.map((item) => ({
        fileName: item.fileName,
        sha256: item.sha256,
        sourceGroup: item.sourceGroup,
        fullyVisibleNails: item.fullyVisibleNails,
        decision: "keep",
        originalResolutionReviewed: true,
        reason: "all visible nails are complete and clear",
      })),
    ],
  });

  return {
    root,
    imageRoot,
    plan,
    authorization,
    screening,
    trainingTruth,
    validationTruth,
    frozen,
    reviews,
    output: path.join(root, "release-role.json"),
  };
}

function run(item: Fixture) {
  return spawnSync(
    python,
    [
      script,
      "--first-annotation-plan",
      item.plan,
      "--authorization",
      item.authorization,
      "--screening-final",
      item.screening,
      "--training-truth-index",
      item.trainingTruth,
      "--validation-truth-index",
      item.validationTruth,
      "--frozen-release-test-manifest",
      item.frozen,
      "--review-decisions",
      item.reviews,
      "--image-root",
      item.imageRoot,
      "--output",
      item.output,
    ],
    { encoding: "utf8" },
  );
}

test("builds exactly 33 release-test candidates by atomically withdrawing a reviewed train group", () => {
  const item = fixture();
  const result = run(item);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.decision, "release_test_role_replacement_manifest_ready_candidate_only");
  assert.deepEqual(report.counts, {
    originalCandidates: 33,
    originalKept: 31,
    originalExcluded: 2,
    replacementImages: 2,
    withdrawnTrainGroups: 1,
    finalImages: 33,
    finalExpectedFullyVisibleNails: 164,
  });
  assert.equal(report.withdrawnTrainGroups[0].allPlanMembersReviewedKeep, true);
  assert.equal(report.withdrawnTrainItems.length, 2);
  assert.ok(
    report.items.every(
      (entry: { assignedRole: string; trainingUse: string; annotationTruthStatus: string }) =>
        entry.assignedRole === "independent-release-test" &&
        entry.trainingUse === "prohibited" &&
        entry.annotationTruthStatus === "not-started",
    ),
  );
  assert.equal(report.inputs.reviewDecisions.sha256, hashFile(item.reviews));
  assert.equal(report.aggregates.finalItemsSha256, canonicalHash(report.items));
  assert.equal(
    report.aggregates.replacementItemsSha256,
    canonicalHash(report.withdrawnTrainItems),
  );
});

test("rejects incomplete original-33 coverage without creating output", () => {
  const item = fixture();
  const reviews = JSON.parse(readFileSync(item.reviews, "utf8"));
  reviews.items.splice(0, 1);
  writeJson(item.reviews, reviews);
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /original 33 review coverage is incomplete/);
  assert.equal(existsSync(item.output), false);
});

test("rejects a decision without original-resolution review", () => {
  const item = fixture();
  const reviews = JSON.parse(readFileSync(item.reviews, "utf8"));
  reviews.items[0].originalResolutionReviewed = false;
  writeJson(item.reviews, reviews);
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /originalResolutionReviewed=true/);
  assert.equal(existsSync(item.output), false);
});

test("rejects a partially reviewed replacement source group", () => {
  const item = fixture();
  const reviews = JSON.parse(readFileSync(item.reviews, "utf8"));
  reviews.items = reviews.items.filter(
    (entry: { fileName: string }) => entry.fileName !== "replacement-2.jpg",
  );
  writeJson(item.reviews, reviews);
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /only partially reviewed/);
  assert.equal(existsSync(item.output), false);
});

test("rejects a replacement source group omitted from plan but present in screening keep", () => {
  const item = fixture();
  const fileName = "replacement-3.jpg";
  const bytes = "replacement-image-3";
  const sha256 = hashBytes(bytes);
  const sourceGroup = "replacement-complete-group";
  writeFileSync(path.join(item.imageRoot, fileName), bytes);

  const authorization = JSON.parse(readFileSync(item.authorization, "utf8"));
  authorization.entries.push({
    fileName,
    sha256,
    sourceGroup,
    trainingUse: "prohibited",
    authorizedUses: [
      "commercial-model-training",
      "independent-release-test",
      "long-term-regression",
    ],
  });
  authorization.entriesSha256 = canonicalHash(authorization.entries);
  writeJson(item.authorization, authorization);

  const screening = JSON.parse(readFileSync(item.screening, "utf8"));
  screening.items.push({
    fileName,
    sha256,
    sourceGroup,
    decision: "keep-for-annotation",
    fullyVisibleNails: 5,
    trainingUse: "prohibited",
    annotationTruthStatus: "not-started",
  });
  writeJson(item.screening, screening);

  const plan = JSON.parse(readFileSync(item.plan, "utf8"));
  plan.inputs.authorizationSha256 = hashFile(item.authorization);
  plan.inputs.screeningBatchSha256 = hashFile(item.screening);
  writeJson(item.plan, plan);

  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /incomplete against screening evidence/);
  assert.equal(existsSync(item.output), false);
});

test("rejects current image SHA drift", () => {
  const item = fixture();
  writeFileSync(path.join(item.imageRoot, "replacement-1.jpg"), "drifted bytes");
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /current source image SHA-256 drift/);
  assert.equal(existsSync(item.output), false);
});

test("rejects overlap with train, val, and frozen evidence", () => {
  for (const target of ["training", "validation", "frozen"] as const) {
    const item = fixture();
    const reviews = JSON.parse(readFileSync(item.reviews, "utf8"));
    const replacement = reviews.items.find(
      (entry: { fileName: string }) => entry.fileName === "replacement-1.jpg",
    );
    const evidencePath =
      target === "training"
        ? item.trainingTruth
        : target === "validation"
          ? item.validationTruth
          : item.frozen;
    const evidence = JSON.parse(readFileSync(evidencePath, "utf8"));
    evidence.items ??= evidence.canonicalTruths;
    evidence.items[0].sourceGroup = replacement.sourceGroup;
    if (target === "frozen") {
      evidence.itemsSha256 = canonicalHash(evidence.items);
    } else {
      evidence.canonicalTruths = evidence.items;
      delete evidence.items;
    }
    writeJson(evidencePath, evidence);
    const result = run(item);
    assert.notEqual(result.status, 0, `${target} unexpectedly passed`);
    assert.match(result.stderr, /identity overlap is not zero/);
    assert.equal(existsSync(item.output), false);
  }
});

test("rejects insufficient replacements and duplicate decisions", () => {
  const insufficient = fixture();
  const insufficientReviews = JSON.parse(readFileSync(insufficient.reviews, "utf8"));
  insufficientReviews.items = insufficientReviews.items.filter(
    (entry: { fileName: string }) => !entry.fileName.startsWith("replacement-"),
  );
  writeJson(insufficient.reviews, insufficientReviews);
  const insufficientResult = run(insufficient);
  assert.notEqual(insufficientResult.status, 0);
  assert.match(insufficientResult.stderr, /replacement count must equal excluded original count/);
  assert.equal(existsSync(insufficient.output), false);

  const duplicate = fixture();
  const duplicateReviews = JSON.parse(readFileSync(duplicate.reviews, "utf8"));
  duplicateReviews.items.push(duplicateReviews.items[0]);
  writeJson(duplicate.reviews, duplicateReviews);
  const duplicateResult = run(duplicate);
  assert.notEqual(duplicateResult.status, 0);
  assert.match(duplicateResult.stderr, /duplicate review decision fileName/);
  assert.equal(existsSync(duplicate.output), false);
});

test("never overwrites an existing output", () => {
  const item = fixture();
  writeFileSync(item.output, "sentinel");
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /output already exists and will not be overwritten/);
  assert.equal(readFileSync(item.output, "utf8"), "sentinel");
});

test("deeply verifies a generated report and rejects evidence or report drift", () => {
  const passing = fixture();
  assert.equal(run(passing).status, 0);
  const verified = spawnSync(python, [script, "--verify-report", passing.output], {
    encoding: "utf8",
  });
  assert.equal(verified.status, 0, verified.stderr || verified.stdout);
  const verification = JSON.parse(verified.stdout);
  assert.equal(verification.decision, "release_test_role_replacement_manifest_verified");
  assert.equal(verification.finalImages, 33);
  assert.equal(verification.reportSha256, hashFile(passing.output));

  writeFileSync(passing.reviews, `${readFileSync(passing.reviews, "utf8")}\n`);
  const inputDrift = spawnSync(python, [script, "--verify-report", passing.output], {
    encoding: "utf8",
  });
  assert.notEqual(inputDrift.status, 0);
  assert.match(inputDrift.stderr, /bound input SHA-256 drift/);

  const tampered = fixture();
  assert.equal(run(tampered).status, 0);
  const report = JSON.parse(readFileSync(tampered.output, "utf8"));
  report.counts.finalImages = 32;
  writeJson(tampered.output, report);
  const reportDrift = spawnSync(python, [script, "--verify-report", tampered.output], {
    encoding: "utf8",
  });
  assert.notEqual(reportDrift.status, 0);
  assert.match(reportDrift.stderr, /report content differs from the replayed current evidence/);
});
