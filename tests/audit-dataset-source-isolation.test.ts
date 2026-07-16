import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-dataset-source-isolation.py");

function fixture(leak = false) {
  const root = mkdtempSync(path.join(tmpdir(), "dataset-source-isolation-"));
  mkdirSync(path.join(root, "images", "val"), { recursive: true });
  const dataset = path.join(root, "dataset.yaml");
  writeFileSync(dataset, `path: ${root.replaceAll("\\", "/")}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: nail_texture\ntask: segment\nclass_count: 1\nimage_size: 512\n`);
  const split = path.join(root, "split.json");
  writeFileSync(split, JSON.stringify({ train: ["train.jpg"], val: ["val.jpg"], test: ["test.jpg"] }));
  const sources = path.join(root, "sources.csv");
  writeFileSync(sources, ["fileName,sourceGroup", `train.jpg,${leak ? "shared" : "train"}`, `val.jpg,${leak ? "shared" : "validation"}`, "test.jpg,test"].join("\n") + "\n");
  return { dataset, split, sources, output: path.join(root, "report.json") };
}

function args(item: ReturnType<typeof fixture>) {
  return [script, "--dataset", item.dataset, "--sources-csv", item.sources, "--split-json", item.split, "--output", item.output];
}

test("approves source groups confined to one split", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(report.decision, "approved_dataset_source_isolation");
  assert.equal(report.leakingGroups.length, 0);
});

test("rejects a source group shared by train and validation", () => {
  const item = fixture(true);
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(report.decision, "rejected_dataset_source_isolation");
  assert.deepEqual(report.leakingGroups[0].splits, ["train", "val"]);
});
