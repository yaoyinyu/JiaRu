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

const python = process.platform === "win32" ? "python" : "python3";
const roleBuilder = path.resolve(
  "model/training/build-release-test-role-replacement-manifest.py",
);
const workspaceBuilder = path.resolve(
  "model/training/build-release-test-annotation-workspace.py",
);
const hashBytes = (value: string) =>
  createHash("sha256").update(value).digest("hex");
const hashFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");
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
const canonicalHash = (value: unknown) =>
  createHash("sha256").update(JSON.stringify(normalize(value))).digest("hex");
const writeJson = (file: string, value: unknown) =>
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);

type Fixture = {
  root: string;
  imageRoot: string;
  roleManifest: string;
  output: string;
  originalFile: string;
  replacementFile: string;
};

function truthItems(prefix: string, count: number) {
  return Array.from({ length: count }, (_, index) => ({
    fileName: `${prefix}-${String(index + 1).padStart(3, "0")}.jpg`,
    imageSha256: hashBytes(`${prefix}-${index + 1}`),
    sourceGroup: `${prefix}-group-${index + 1}`,
    completeMaskCount: 5,
  }));
}

function fixture(): Fixture {
  const root = mkdtempSync(path.join(tmpdir(), "release-annotation-workspace-"));
  const imageRoot = path.join(root, "source-images");
  mkdirSync(imageRoot);
  const originals = Array.from({ length: 33 }, (_, index) => {
    const fileName = `original-${String(index + 1).padStart(2, "0")}.jpg`;
    const bytes = `original-${index + 1}`;
    writeFileSync(path.join(imageRoot, fileName), bytes);
    return {
      fileName,
      sha256: hashBytes(bytes),
      sourceGroup: `original-group-${Math.floor(index / 3) + 1}`,
      assignedRole: "independent-release-test",
      firstAnnotationBatch: false,
      fullyVisibleNails: 5,
      trainingUse: "prohibited",
      annotationTruthStatus: "not-started",
    };
  });
  const replacementGroupSizes = [3, 2, 2, 1];
  const replacements: Array<Record<string, unknown>> = [];
  let replacementIndex = 0;
  replacementGroupSizes.forEach((size, groupIndex) => {
    for (let member = 0; member < size; member += 1) {
      replacementIndex += 1;
      const fileName = `replacement-${replacementIndex}.jpg`;
      const bytes = `replacement-${replacementIndex}`;
      writeFileSync(path.join(imageRoot, fileName), bytes);
      replacements.push({
        fileName,
        sha256: hashBytes(bytes),
        sourceGroup: `replacement-group-${groupIndex + 1}`,
        assignedRole: "train",
        firstAnnotationBatch: false,
        fullyVisibleNails: replacementIndex === 8 ? 10 : 5,
        trainingUse: "prohibited",
        annotationTruthStatus: "not-started",
      });
    }
  });
  const planItems = [...originals, ...replacements];
  const entries = planItems.map((item) => ({
    fileName: item.fileName,
    sha256: item.sha256,
    sourceGroup: item.sourceGroup,
    trainingUse: "prohibited",
    authorizedUses: ["independent-release-test", "commercial-model-training"],
  }));
  const authorization = path.join(root, "authorization.json");
  writeJson(authorization, {
    ok: true,
    root: imageRoot,
    authorization: {
      decision: "A",
      status: "confirmed",
      authorizedUses: ["independent-release-test", "commercial-model-training"],
    },
    entriesSha256: canonicalHash(entries),
    entries,
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
  const train = path.join(root, "train.json");
  writeJson(train, {
    ok: true,
    decision: "approved_unique_training_truth_index",
    summary: { uniqueImageCount: 100, conflictingImageCount: 0 },
    canonicalTruths: truthItems("train", 100),
  });
  const val = path.join(root, "val.json");
  writeJson(val, {
    ok: true,
    decision: "approved_unique_validation_truth_index",
    summary: { uniqueImageCount: 30, conflictingImageCount: 0 },
    canonicalTruths: truthItems("val", 30),
  });
  const frozen = path.join(root, "frozen.json");
  const frozenItems = truthItems("frozen", 67).map((item) => ({
    ...item,
    parentFileName: item.fileName,
    parentSourceGroup: item.sourceGroup,
    trainingUse: "prohibited",
  }));
  writeJson(frozen, {
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
      ...originals.map((item, index) => ({
        fileName: item.fileName,
        sha256: item.sha256,
        sourceGroup: item.sourceGroup,
        fullyVisibleNails: item.fullyVisibleNails,
        decision: index < 25 ? "keep" : "exclude",
        originalResolutionReviewed: true,
        reason: index < 25 ? "complete" : "incomplete",
      })),
      ...replacements.map((item) => ({
        fileName: item.fileName,
        sha256: item.sha256,
        sourceGroup: item.sourceGroup,
        fullyVisibleNails: item.fullyVisibleNails,
        decision: "keep",
        originalResolutionReviewed: true,
        reason: "complete replacement",
      })),
    ],
  });
  const roleManifest = path.join(root, "role-manifest.json");
  const roleResult = spawnSync(
    python,
    [
      roleBuilder,
      "--first-annotation-plan",
      plan,
      "--authorization",
      authorization,
      "--screening-final",
      screening,
      "--training-truth-index",
      train,
      "--validation-truth-index",
      val,
      "--frozen-release-test-manifest",
      frozen,
      "--review-decisions",
      reviews,
      "--image-root",
      imageRoot,
      "--output",
      roleManifest,
    ],
    { encoding: "utf8" },
  );
  assert.equal(roleResult.status, 0, roleResult.stderr || roleResult.stdout);
  return {
    root,
    imageRoot,
    roleManifest,
    output: path.join(root, "workspace"),
    originalFile: path.join(imageRoot, "original-01.jpg"),
    replacementFile: path.join(imageRoot, "replacement-1.jpg"),
  };
}

function run(item: Fixture) {
  return spawnSync(
    python,
    [
      workspaceBuilder,
      "--role-replacement-manifest",
      item.roleManifest,
      "--output-dir",
      item.output,
      "--target-shard-size",
      "4",
    ],
    { encoding: "utf8" },
  );
}

test("builds and deeply verifies a source-group-atomic 33-image workspace", () => {
  const item = fixture();
  const result = run(item);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const manifestPath = path.join(item.output, "annotation-workspace-manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  assert.equal(manifest.decision, "annotation_workspace_ready_candidate_only");
  assert.equal(manifest.counts.images, 33);
  assert.equal(manifest.counts.expectedFullyVisibleNails, 170);
  assert.ok(manifest.items.every((entry: { assignedRole: string; trainingUse: string; annotationTruthStatus: string }) => (
    entry.assignedRole === "independent-release-test" &&
    entry.trainingUse === "prohibited" &&
    entry.annotationTruthStatus === "not-started"
  )));
  const groupShards = new Map<string, Set<number>>();
  for (const entry of manifest.items) {
    const shards = groupShards.get(entry.sourceGroup) ?? new Set<number>();
    shards.add(entry.shardIndex);
    groupShards.set(entry.sourceGroup, shards);
    assert.equal(hashFile(entry.workspacePath), entry.sha256);
  }
  assert.ok([...groupShards.values()].every((shards) => shards.size === 1));
  const downstreamDir = path.join(item.output, "mask-review-finalization-v1");
  mkdirSync(downstreamDir);
  writeFileSync(path.join(downstreamDir, "derived-review.json"), "{}\n");
  const verified = spawnSync(
    python,
    [workspaceBuilder, "--verify-workspace-manifest", manifestPath],
    { encoding: "utf8" },
  );
  assert.equal(verified.status, 0, verified.stderr || verified.stdout);
  assert.equal(JSON.parse(verified.stdout).images, 33);
});

test("rejects a missing source image without creating output", () => {
  const item = fixture();
  rmSync(item.originalFile);
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /deep verifier rejected input/);
  assert.equal(existsSync(item.output), false);
});

test("rejects source image hash drift without creating output", () => {
  const item = fixture();
  writeFileSync(item.replacementFile, "drifted");
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /deep verifier rejected input/);
  assert.equal(existsSync(item.output), false);
});

test("rejects a partial source group in the role manifest", () => {
  const item = fixture();
  const role = JSON.parse(readFileSync(item.roleManifest, "utf8"));
  role.items = role.items.filter(
    (entry: { fileName: string }) => entry.fileName !== "replacement-1.jpg",
  );
  writeJson(item.roleManifest, role);
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /deep verifier rejected input/);
  assert.equal(existsSync(item.output), false);
});

test("rejects a non-empty output directory", () => {
  const item = fixture();
  mkdirSync(item.output);
  writeFileSync(path.join(item.output, "sentinel"), "keep");
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /output directory must be absent or empty/);
  assert.equal(readFileSync(path.join(item.output, "sentinel"), "utf8"), "keep");
});

test("rejects a forged role manifest", () => {
  const item = fixture();
  const role = JSON.parse(readFileSync(item.roleManifest, "utf8"));
  role.ok = false;
  writeJson(item.roleManifest, role);
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /deep verifier rejected input/);
  assert.equal(existsSync(item.output), false);
});
