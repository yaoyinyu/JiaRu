import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-real-material-annotation-workspace.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("annotation workspace binds source hashes and keeps source groups in one shard", () => {
  const root = mkdtempSync(path.join(tmpdir(), "annotation-workspace-"));
  const images = path.join(root, "images");
  mkdirSync(images);
  const files = ["a.jpg", "b.jpg", "c.jpg"];
  files.forEach((file, index) => execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(64,96),(${index + 10},20,30)).save(r'${path.join(images, file)}')`]));
  const entries = files.map((fileName, index) => ({
    fileName,
    sha256: hash(path.join(images, fileName)),
    sourceGroup: index < 2 ? "group-a" : "group-b",
    trainingUse: "prohibited",
  }));
  const authorization = path.join(root, "authorization.json");
  writeFileSync(authorization, JSON.stringify({ ok: true, root: images, authorization: { decision: "A" }, entries }));
  const plan = path.join(root, "plan.json");
  writeFileSync(plan, JSON.stringify({
    ok: true,
    decision: "first_annotation_batch_plan_ready_mask_review_required",
    inputs: { authorizationSha256: hash(authorization) },
    counts: { firstAnnotationBatchImages: 3 },
    items: entries.map((entry) => ({
      ...entry,
      assignedRole: "train",
      firstAnnotationBatch: true,
      fullyVisibleNails: 5,
      annotationTruthStatus: "not-started",
    })),
  }));
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--plan", plan, "--authorization", authorization, "--output-dir", output, "--target-shard-size", "2"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const manifest = JSON.parse(readFileSync(path.join(output, "annotation-workspace-manifest.json"), "utf8"));
  assert.equal(manifest.counts.images, 3);
  assert.equal(manifest.counts.sourceGroups, 2);
  assert.equal(manifest.counts.expectedFullyVisibleNails, 15);
  assert.equal(manifest.counts.shards, 2);
  const groupShards = new Map<string, Set<number>>();
  for (const item of manifest.items) {
    const shards = groupShards.get(item.sourceGroup) ?? new Set<number>();
    shards.add(item.shardIndex);
    groupShards.set(item.sourceGroup, shards);
    assert.equal(hash(item.workspacePath), item.sha256);
    assert.equal(item.trainingUse, "prohibited");
  }
  assert.ok([...groupShards.values()].every((shards) => shards.size === 1));
});
