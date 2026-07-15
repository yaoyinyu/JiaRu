import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-real-material-candidate-intake.py");

function sha256(filePath: string) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "real-material-candidate-"));
  const imageRoot = path.join(root, "images");
  mkdirSync(imageRoot);
  const names = ["nail_00001_note-a_0.jpg", "nail_00002_note-a_1.jpg", "nail_00003_note-b_0.jpg"];
  names.forEach((name, index) => {
    execFileSync("python", [
      "-c",
      `from PIL import Image; Image.new('RGB', (64, 96), (${100 + index}, 120, 140)).save(r'${path.join(imageRoot, name)}')`,
    ]);
  });
  const audit = path.join(root, "audit.json");
  writeFileSync(
    audit,
    JSON.stringify({
      ok: true,
      root: imageRoot,
      totals: {
        validImages: 3,
        invalidImages: 0,
        exactDuplicateGroups: 0,
        nearDuplicatePairs: 1,
      },
      comparisons: { referenceImages: 5, exactMatches: [], nearMatches: [{ distance: 1 }] },
      images: names.map((name) => ({
        path: name,
        sha256: sha256(path.join(imageRoot, name)),
        dhash: "0".repeat(16),
        width: 64,
        height: 96,
      })),
    }),
  );
  return { root, imageRoot, audit, output: path.join(root, "intake.json") };
}

function args(item: ReturnType<typeof fixture>) {
  return [
    script,
    "--audit",
    item.audit,
    "--root",
    item.imageRoot,
    "--batch-id",
    "real-material-test",
    "--output",
    item.output,
  ];
}

test("real material candidate intake groups images by note and prohibits training", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const document = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(document.ok, true);
  assert.equal(document.counts.images, 3);
  assert.equal(document.counts.sourceGroups, 2);
  assert.equal(document.authorization.status, "pending-user-confirmation");
  assert.equal(document.authorization.trainingUse, "prohibited");
  assert.equal(document.entries[0].sourceGroup, document.entries[1].sourceGroup);
  assert.notEqual(document.entries[0].sourceGroup, document.entries[2].sourceGroup);
  assert.ok(document.entries.every((entry: { trainingUse: string }) => entry.trainingUse === "prohibited"));
});

test("real material candidate intake rejects an image that changed after audit", () => {
  const item = fixture();
  writeFileSync(path.join(item.imageRoot, "nail_00001_note-a_0.jpg"), "changed");
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const document = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(document.ok, false);
  assert.match(document.errors.join("\n"), /sha256 drift/);
});
