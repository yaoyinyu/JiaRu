import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { writeTestPng } from "./helpers/hard-negative-evidence.ts";

const script = path.resolve(
  "model/training/finalize-reviewed-hard-negative-manifest.py",
);
const python = process.env.PYTHON ?? "python";
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
  return JSON.stringify(value);
};

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function fixture(count: number, mismatchedFirstExtension = false) {
  const root = mkdtempSync(path.join(tmpdir(), "hard-negative-finalizer-"));
  const images = path.join(root, "images");
  mkdirSync(images, { recursive: true });
  const screening = path.join(root, "screening.json");
  const authorization = path.join(root, "authorization.json");
  writeJson(screening, { ok: true, decision: "source-screening-pass" });
  writeJson(authorization, {
    ok: true,
    decision: "A",
    authorizedUses: ["commercial-model-training"],
  });

  const reviewedCandidates = Array.from({ length: count }, (_, index) => {
    const id = String(index + 1).padStart(3, "0");
    const fileName =
      mismatchedFirstExtension && index === 0
        ? `negative-${id}.jpg`
        : `negative-${id}.png`;
    const sourcePath = path.join(images, fileName);
    writeTestPng(sourcePath, index + 1);
    const sha256 = shaFile(sourcePath);
    return {
      fileName,
      sourcePath,
      sha256,
      width: 320,
      height: 320,
      sourceGroup: `hard-negative-group-${id}`,
      originalResolutionVisualReview: {
        reviewed: true,
        clearEnoughForHardNegative: true,
        validHumanManicureSurfaceAnywhere: false,
        croppedTargetNail: false,
        collage: false,
        templateOrIndependentNailTip: false,
        reviewNote: "Clear single deployment-like scene without a human nail surface.",
      },
      authorizationEvidence: {
        decision: "A",
        authorizationEntryFileNameMatch: true,
        authorizationEntrySha256Match: true,
        trainingEligibility: "permitted-after-visual-review-and-source-isolation",
      },
      sourceIsolationEvidence: {
        trainImageShaMatches: 0,
        validationImageShaMatches: 0,
        frozenTestImageShaMatches: 0,
        isolated: true,
      },
      role: "hard-negative-candidate",
      trainingUse: "prohibited",
      materializationStatus: "not-materialized",
      candidateStatus: "pass-candidate-only",
    };
  });
  const review = path.join(root, "review.json");
  writeJson(review, {
    ok: true,
    decision: "hard_negative_candidate_scan_complete_candidate_only",
    inputs: {
      sourceScreeningBatch: {
        path: screening,
        sha256: shaFile(screening),
      },
      authorization: {
        path: authorization,
        sha256: shaFile(authorization),
        decision: "A",
        status: "confirmed",
        authorizedUses: [
          "commercial-model-training",
          "independent-release-test",
          "long-term-regression",
        ],
      },
    },
    policy: {
      candidateMustBeClear: true,
      candidateMustContainNoValidHumanManicureSurfaceAnywhere: true,
      candidateMustBeUsefulForDeploymentFalsePositiveSuppression: true,
      candidateMustHaveAuthorizationA: true,
      candidateMustBeSourceIsolatedFromTrainValAndFrozenTest: true,
      rejectTemplates: true,
      rejectIndependentNailTips: true,
      rejectCollages: true,
      rejectLowQuality: true,
      rejectCroppedSources: true,
      candidateOnly: true,
      trainingUse: "prohibited-until-separate-materialization-and-training-authorization",
    },
    candidates: reviewedCandidates,
  });

  const candidates = reviewedCandidates.map((item) => ({
    fileName: item.fileName,
    sourcePath: item.sourcePath,
    sha256: item.sha256,
    sourceGroup: item.sourceGroup,
    authorization: "A",
    sourceIsolation: "verified-zero-match-train-val-frozen-test",
    humanManicureSurfaceAnywhere: false,
    candidatePurpose: "deployment-false-positive-suppression",
    role: "hard-negative-candidate",
    trainingUse: "prohibited",
    materializationStatus: "not-materialized",
  }));
  const manifest = path.join(root, "candidate-manifest.json");
  writeJson(manifest, {
    ok: true,
    decision: "hard_negative_candidate_manifest_ready_not_materialized",
    candidateOnly: true,
    inputs: {
      reviewDecisionsPath: review,
      reviewDecisionsSha256: shaFile(review),
      sourceScreeningBatchPath: screening,
      sourceScreeningBatchSha256: shaFile(screening),
      authorizationPath: authorization,
      authorizationSha256: shaFile(authorization),
    },
    summary: {
      reviewedImages: count,
      candidateImages: count,
      safeHardNegativeCount: count,
      excludedImages: 0,
    },
    candidates,
    gates: {
      allThirtySevenOriginalResolutionReviewed: true,
      allSourceImageHashesMatchBoundScreeningEvidence: true,
      allRelevantShardReportAndDecisionHashesMatch: true,
      authorizationAConfirmed: true,
      candidateSourceIsolatedFromTrain: true,
      candidateSourceIsolatedFromVal: true,
      candidateSourceIsolatedFromFrozenTest: true,
      officialDatasetUnchanged: true,
      sharedSplitUnchanged: true,
      trainingStillProhibited: true,
    },
  });
  return { root, manifest, review, reviewedCandidates };
}

function run(manifest: string, output: string, extra: string[] = []) {
  return spawnSync(
    python,
    [script, "--candidate-manifest", manifest, "--output", output, ...extra],
    { encoding: "utf8" },
  );
}

test("approves exactly 100 fully reviewed hard negatives", () => {
  const data = fixture(100, true);
  const output = path.join(data.root, "approved.json");
  const result = run(data.manifest, output);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.status, "PASS");
  assert.equal(report.decision, "approved_hard_negative_manifest");
  assert.equal(report.trainingUse, "permitted");
  assert.equal(report.summary.reviewedHardNegativeImages, 100);
  assert.equal(report.summary.gapToMinimum, 0);
  assert.equal(report.schemaVersion, 2);
  assert.equal(report.items.length, 100);
  assert.equal(report.items[0].sourceFileName, "negative-001.jpg");
  assert.equal(report.items[0].fileName, "negative-001.png");
  assert.equal(report.items[0].imageFormat, "PNG");
  assert.equal(report.items[0].sourceExtensionMatchesFormat, false);
  assert.ok(report.items.every((item: { trainingUse: string }) => item.trainingUse === "permitted"));
  assert.equal(
    report.itemsSha256,
    createHash("sha256").update(canonical(report.items)).digest("hex"),
  );
});

test("writes HOLD and keeps an insufficient pool prohibited", () => {
  const data = fixture(99);
  const output = path.join(data.root, "hold.json");
  const result = run(data.manifest, output);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, false);
  assert.equal(report.status, "HOLD");
  assert.equal(report.decision, "hold_insufficient_hard_negatives");
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.summary.gapToMinimum, 1);
  assert.equal(report.items, undefined);
  assert.equal(report.candidateItems.length, 99);
  assert.ok(
    report.candidateItems.every(
      (item: { trainingUse: string }) => item.trainingUse === "prohibited",
    ),
  );
});

test("rejects a visual review that permits a human manicure surface", () => {
  const data = fixture(100);
  const review = JSON.parse(readFileSync(data.review, "utf8"));
  review.candidates[0].originalResolutionVisualReview.validHumanManicureSurfaceAnywhere = true;
  writeJson(data.review, review);
  const manifest = JSON.parse(readFileSync(data.manifest, "utf8"));
  manifest.inputs.reviewDecisionsSha256 = shaFile(data.review);
  writeJson(data.manifest, manifest);
  const output = path.join(data.root, "rejected.json");
  const result = run(data.manifest, output);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /validHumanManicureSurfaceAnywhere/);
});

test("rejects review evidence drift and image byte drift", () => {
  const reviewData = fixture(100);
  writeFileSync(reviewData.review, `${readFileSync(reviewData.review, "utf8")}\n`);
  const reviewResult = run(
    reviewData.manifest,
    path.join(reviewData.root, "review-drift.json"),
  );
  assert.notEqual(reviewResult.status, 0);
  assert.match(reviewResult.stderr, /review decisions SHA-256 drift/);

  const imageData = fixture(100);
  writeFileSync(imageData.reviewedCandidates[0].sourcePath, "changed-image-bytes\n");
  const imageResult = run(
    imageData.manifest,
    path.join(imageData.root, "image-drift.json"),
  );
  assert.notEqual(imageResult.status, 0);
  assert.match(imageResult.stderr, /image SHA-256 drift/);
});

test("replays approved evidence and rejects post-approval drift", () => {
  const data = fixture(100);
  const output = path.join(data.root, "approved.json");
  assert.equal(run(data.manifest, output).status, 0);
  const verified = spawnSync(
    python,
    [script, "--verify-report", output],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr);
  writeFileSync(data.reviewedCandidates[0].sourcePath, "not-an-image");
  const drifted = spawnSync(
    python,
    [script, "--verify-report", output],
    { encoding: "utf8" },
  );
  assert.notEqual(drifted.status, 0);
  assert.match(drifted.stderr, /image SHA-256 drift/);
});

test("rejects a text file disguised as an image", () => {
  const data = fixture(100);
  const review = JSON.parse(readFileSync(data.review, "utf8"));
  writeFileSync(data.reviewedCandidates[0].sourcePath, "plain text pretending to be PNG");
  const changedHash = shaFile(data.reviewedCandidates[0].sourcePath);
  review.candidates[0].sha256 = changedHash;
  writeJson(data.review, review);
  const manifest = JSON.parse(readFileSync(data.manifest, "utf8"));
  manifest.inputs.reviewDecisionsSha256 = shaFile(data.review);
  manifest.candidates[0].sha256 = changedHash;
  writeJson(data.manifest, manifest);
  const result = run(data.manifest, path.join(data.root, "disguised.json"));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /cannot be fully decoded/);
});

test("cannot lower the formal 100-image gate", () => {
  const data = fixture(1);
  const output = path.join(data.root, "lowered.json");
  const result = run(data.manifest, output, ["--minimum-images", "1"]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /cannot lower the formal 100-image/);
});

test("never overwrites candidate, review, or image evidence", () => {
  const data = fixture(100);
  const originalManifest = readFileSync(data.manifest);
  const candidateResult = spawnSync(
    python,
    [
      script,
      "--candidate-manifest",
      data.manifest,
      "--output",
      data.manifest,
      "--overwrite",
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(candidateResult.status, 0);
  assert.match(candidateResult.stderr, /must not overwrite an input evidence/);
  assert.deepEqual(readFileSync(data.manifest), originalManifest);
});
