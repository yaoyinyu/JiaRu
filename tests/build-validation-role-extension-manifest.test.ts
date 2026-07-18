import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";

const script = path.resolve("model/training/build-validation-role-extension-manifest.py");
const hashFile = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");
const canonicalHash = (value: unknown) => {
  const normalize = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(normalize);
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right)).map(([key, child]) => [key, normalize(child)]));
    }
    return item;
  };
  return createHash("sha256").update(JSON.stringify(normalize(value))).digest("hex");
};

type Fixture = {
  root: string;
  imageRoot: string;
  base: string;
  plan: string;
  truth: string;
  decisions: string;
  authorization: string;
  output: string;
};

async function fixture(): Promise<Fixture> {
  const root = mkdtempSync(path.join(tmpdir(), "validation-role-extension-"));
  const imageRoot = path.join(root, "source-images");
  const baseRoot = path.join(root, "base-workspace");
  mkdirSync(imageRoot);
  mkdirSync(path.join(baseRoot, "images"), { recursive: true });
  await sharp({ create: { width: 32, height: 48, channels: 3, background: "red" } }).jpeg().toFile(path.join(imageRoot, "base.jpg"));
  await sharp({ create: { width: 32, height: 48, channels: 3, background: "green" } }).jpeg().toFile(path.join(imageRoot, "replacement-a.jpg"));
  await sharp({ create: { width: 32, height: 48, channels: 3, background: "blue" } }).jpeg().toFile(path.join(imageRoot, "replacement-b.jpg"));
  writeFileSync(path.join(baseRoot, "images", "base.jpg"), readFileSync(path.join(imageRoot, "base.jpg")));

  const identities = [
    { fileName: "base.jpg", sha256: hashFile(path.join(imageRoot, "base.jpg")), sourceGroup: "group-val", trainingUse: "prohibited" },
    { fileName: "replacement-a.jpg", sha256: hashFile(path.join(imageRoot, "replacement-a.jpg")), sourceGroup: "group-replacement", trainingUse: "prohibited" },
    { fileName: "replacement-b.jpg", sha256: hashFile(path.join(imageRoot, "replacement-b.jpg")), sourceGroup: "group-replacement", trainingUse: "prohibited" },
  ];
  const authorization = path.join(root, "authorization.json");
  writeFileSync(authorization, JSON.stringify({
    ok: true,
    root: imageRoot,
    authorization: { status: "confirmed", decision: "A", authorizedUses: ["commercial-model-training"] },
    entriesSha256: canonicalHash(identities),
    entries: identities,
  }));
  const plan = path.join(root, "plan.json");
  writeFileSync(plan, JSON.stringify({
    ok: true,
    decision: "first_annotation_batch_plan_ready_mask_review_required",
    inputs: { authorizationSha256: hashFile(authorization) },
    policy: { sourceGroupAtomicAcrossRoles: true },
    items: [
      { ...identities[0], assignedRole: "val", firstAnnotationBatch: false, fullyVisibleNails: 5, annotationTruthStatus: "not-started" },
      { ...identities[1], assignedRole: "train", firstAnnotationBatch: false, fullyVisibleNails: 5, annotationTruthStatus: "not-started" },
      { ...identities[2], assignedRole: "train", firstAnnotationBatch: false, fullyVisibleNails: 4, annotationTruthStatus: "not-started" },
    ],
  }));
  const base = path.join(baseRoot, "annotation-workspace-manifest.json");
  writeFileSync(base, JSON.stringify({
    ok: true,
    decision: "annotation_workspace_ready_candidate_only",
    inputs: { planSha256: hashFile(plan), authorizationSha256: hashFile(authorization) },
    policy: { selectionMode: "val", assignedRole: "val" },
    counts: { images: 1, sourceGroups: 1, shards: 1, expectedFullyVisibleNails: 5, materializationMethods: { hardlink: 1 } },
    shards: [{ index: 1, images: 1, sourceGroups: ["group-val"] }],
    items: [{
      ...identities[0],
      assignedRole: "val",
      expectedFullyVisibleNails: 5,
      workspacePath: path.join(baseRoot, "images", "base.jpg"),
      annotationTruthStatus: "not-started",
    }],
  }));
  const truth = path.join(root, "training-truth-index.json");
  writeFileSync(truth, JSON.stringify({
    ok: true,
    decision: "approved_unique_training_truth_index",
    summary: { conflictingImageCount: 0 },
    canonicalTruths: [{ fileName: "other.jpg", sourceGroup: "group-other" }],
  }));
  const decisions = path.join(root, "replacement-decisions.json");
  writeFileSync(decisions, JSON.stringify({
    ok: true,
    decision: "reviewed_validation_replacements_pass",
    policy: {
      originalResolutionReviewCompleted: true,
      wholeVisibleNailSurfaceRequired: true,
      sourceGroupAtomicReassignmentRequested: true,
    },
    items: [
      { ...identities[1], fullyVisibleNails: 5, reviewStatus: "pass", replacementReason: "replace a cropped original val image" },
      { ...identities[2], fullyVisibleNails: 4, reviewStatus: "pass", replacementReason: "replace an occluded original val image" },
    ],
  }));
  return { root, imageRoot, base, plan, truth, decisions, authorization, output: path.join(root, "combined.json") };
}

function run(item: Fixture) {
  return spawnSync("python", [
    script,
    "--base-role-manifest", item.base,
    "--plan", item.plan,
    "--training-truth-index", item.truth,
    "--replacement-decisions", item.decisions,
    "--authorization", item.authorization,
    "--image-root", item.imageRoot,
    "--output", item.output,
  ], { encoding: "utf8" });
}

test("builds a hash-bound combined val role manifest by reassigning a whole source group", async () => {
  const item = await fixture();
  const result = run(item);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(report.policy.selectionMode, "val");
  assert.equal(report.policy.assignedRole, "val");
  assert.equal(report.counts.baseImages, 1);
  assert.equal(report.counts.addedImages, 2);
  assert.equal(report.counts.combinedImages, 3);
  assert.equal(report.counts.addedExpectedFullyVisibleNails, 9);
  assert.equal(report.inputs.baseRoleManifestSha256, hashFile(item.base));
  assert.equal(report.inputs.trainingTruthIndexSha256, hashFile(item.truth));
  assert.deepEqual(report.extension.sourceGroupReassignments[0].originalAssignedRoles, ["train"]);
  assert.equal(report.extension.sourceGroupReassignments[0].allPlanItemsCovered, true);
  assert.ok(report.items.slice(1).every((entry: { assignedRole: string; trainingUse: string; annotationTruthStatus: string }) => (
    entry.assignedRole === "val" && entry.trainingUse === "prohibited" && entry.annotationTruthStatus === "not-started"
  )));
});

test("rejects the entire selected source group when any approved train truth uses it", async () => {
  const item = await fixture();
  const truth = JSON.parse(readFileSync(item.truth, "utf8"));
  truth.canonicalTruths.push({ fileName: "already-trained.jpg", sourceGroup: "group-replacement" });
  writeFileSync(item.truth, JSON.stringify(truth));
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /whole group is rejected/);
  const rejection = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(rejection.ok, false);
});

test("rejects the entire selected source group when it was materialized in the first train annotation batch", async () => {
  const item = await fixture();
  const plan = JSON.parse(readFileSync(item.plan, "utf8"));
  plan.items[1].firstAnnotationBatch = true;
  plan.items[2].firstAnnotationBatch = true;
  writeFileSync(item.plan, JSON.stringify(plan));
  const base = JSON.parse(readFileSync(item.base, "utf8"));
  base.inputs.planSha256 = hashFile(item.plan);
  writeFileSync(item.base, JSON.stringify(base));
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /already materialized in the first train annotation batch/);
});

test("rejects replacement source image SHA drift", async () => {
  const item = await fixture();
  writeFileSync(path.join(item.imageRoot, "replacement-a.jpg"), "changed");
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /SHA-256 drifted/);
});

test("rejects duplicate replacements within one batch", async () => {
  const item = await fixture();
  const decisions = JSON.parse(readFileSync(item.decisions, "utf8"));
  decisions.items.push(decisions.items[0]);
  writeFileSync(item.decisions, JSON.stringify(decisions));
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /duplicate or empty fileName/);
});

test("rejects a replacement that did not pass original-resolution review", async () => {
  const item = await fixture();
  const decisions = JSON.parse(readFileSync(item.decisions, "utf8"));
  decisions.items[0].reviewStatus = "rework";
  writeFileSync(item.decisions, JSON.stringify(decisions));
  const result = run(item);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /not an original-resolution visual-review pass/);
});
