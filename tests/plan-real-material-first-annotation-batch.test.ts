import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/plan-real-material-first-annotation-batch.py");
test("first annotation planner keeps roles and the first batch source-group atomic", () => {
  const root = mkdtempSync(path.join(tmpdir(), "first-annotation-plan-"));
  const entries = Array.from({ length: 9 }, (_, index) => ({
    fileName: `nail_${index}.jpg`,
    sha256: `hash-${index}`,
    sourceGroup: `group-${index}`,
    trainingUse: "prohibited",
  }));
  const canonical = (value: unknown) => {
    const sort = (item: unknown): unknown => Array.isArray(item)
      ? item.map(sort)
      : item && typeof item === "object"
        ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, sort(child)]))
        : item;
    return createHash("sha256").update(JSON.stringify(sort(value))).digest("hex");
  };
  const authorization = path.join(root, "authorization.json");
  writeFileSync(authorization, JSON.stringify({
    ok: true,
    authorization: { decision: "A", status: "confirmed" },
    entries,
    entriesSha256: canonical(entries),
  }));
  const screening = path.join(root, "screening.json");
  writeFileSync(screening, JSON.stringify({
    ok: true,
    decision: "source_screening_batch_pass",
    items: entries.slice(1).map((entry) => ({
      ...entry,
      decision: "keep-for-annotation",
      fullyVisibleNails: 5,
      annotationTruthStatus: "not-started",
    })),
  }));
  const near = path.join(root, "near.json");
  writeFileSync(near, JSON.stringify({
    ok: true,
    decision: "near_duplicate_visual_review_pass",
    excludedCandidates: [{ fileName: entries[0].fileName, reason: "duplicate" }],
  }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [
    script,
    "--authorization", authorization,
    "--screening-batch", screening,
    "--near-duplicate-final", near,
    "--output-dir", output,
    "--release-test-target", "2",
    "--val-target", "2",
    "--train-annotation-target", "3",
    "--train-annotation-min", "2",
    "--train-annotation-max", "4",
  ], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const plan = JSON.parse(readFileSync(path.join(output, "first-annotation-batch-plan.json"), "utf8"));
  assert.equal(plan.counts.byRole["independent-release-test"], 2);
  assert.equal(plan.counts.byRole.val, 2);
  assert.equal(plan.counts.firstAnnotationBatchImages, 3);
  assert.equal(plan.counts.firstAnnotationBatchExpectedNails, 15);
  assert.ok(plan.items.every((item: { trainingUse: string }) => item.trainingUse === "prohibited"));
  for (const group of plan.roleSourceGroups.firstAnnotationBatch) {
    assert.ok(plan.items.filter((item: { sourceGroup: string }) => item.sourceGroup === group).every((item: { firstAnnotationBatch: boolean }) => item.firstAnnotationBatch));
  }
});
