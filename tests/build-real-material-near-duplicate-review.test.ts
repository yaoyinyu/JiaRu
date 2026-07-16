import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const authorizeScript = path.resolve("model/training/authorize-real-material-candidate-intake.py");
const script = path.resolve("model/training/build-real-material-near-duplicate-review.py");

function sha256(filePath: string) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

test("near-duplicate review builds auditable pair sheets without auto-excluding", () => {
  const root = mkdtempSync(path.join(tmpdir(), "near-duplicate-review-"));
  const images = path.join(root, "images");
  const refs = path.join(root, "refs");
  mkdirSync(images);
  mkdirSync(refs);
  const files = ["nail_00001_note-a_0.jpg", "nail_00002_note-b_0.jpg"];
  for (const fileName of files) {
    execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(64,96),(100,120,140)).save(r'${path.join(images, fileName)}')`]);
  }
  execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(64,96),(100,120,140)).save(r'${path.join(refs, "old.jpg")}')`]);
  const intake = path.join(root, "intake.json");
  writeFileSync(intake, JSON.stringify({
    schemaVersion: 1, batchId: "test", ok: true, root: images,
    authorization: { status: "pending-user-confirmation", authorizedUses: [], trainingUse: "prohibited" },
    status: "candidate_inventory_pass_authorization_and_visual_review_pending",
    counts: { images: 2, sourceGroups: 2 },
    entries: files.map((fileName, index) => ({ fileName, sha256: sha256(path.join(images, fileName)), sourceGroup: `g${index}`, trainingUse: "prohibited" })),
  }), "utf8");
  const authorization = path.join(root, "authorization.json");
  execFileSync("python", [authorizeScript, "--intake", intake, "--decision", "A", "--confirmed-by", "user", "--confirmation-note", "A", "--output", authorization]);
  const corpus = path.join(root, "corpus.json");
  writeFileSync(corpus, JSON.stringify({
    ok: true, root: images, totals: { validImages: 2 },
    nearDuplicatePairs: [{ left: files[0], right: files[1], distance: 0 }],
    comparisons: { nearMatches: [{ candidate: files[0], referenceRoot: refs, reference: "old.jpg", distance: 0 }] },
  }), "utf8");
  const output = path.join(root, "output");
  const result = spawnSync("python", [script, "--authorization", authorization, "--corpus-audit", corpus, "--output-dir", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(output, "near-duplicate-review-report.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.pairs, 2);
  assert.equal(report.counts.highSimilarityPairs, 2);
  assert.equal(report.policy.dhashAloneCannotExclude, true);
  const csv = readFileSync(report.reviewCsv, "utf8");
  assert.match(csv, /manual-visual-review|exclude-new-candidate/);
  assert.ok(!csv.includes(",exclude,"));
  assert.equal(report.pages.length, 1);
});
