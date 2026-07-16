import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/authorize-real-material-candidate-intake.py");

function sha256(filePath: string) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "real-material-authorization-"));
  const imageRoot = path.join(root, "images");
  mkdirSync(imageRoot);
  const fileName = "nail_00001_note-a_0.jpg";
  const imagePath = path.join(imageRoot, fileName);
  execFileSync("python", [
    "-c",
    `from PIL import Image; Image.new('RGB', (64, 96), (100, 120, 140)).save(r'${imagePath}')`,
  ]);
  const intakePath = path.join(root, "candidate-intake.json");
  writeFileSync(
    intakePath,
    JSON.stringify({
      schemaVersion: 1,
      batchId: "real-material-test",
      ok: true,
      root: imageRoot,
      authorization: {
        status: "pending-user-confirmation",
        authorizedUses: [],
        trainingUse: "prohibited",
      },
      status: "candidate_inventory_pass_authorization_and_visual_review_pending",
      counts: { images: 1, sourceGroups: 1 },
      entries: [
        {
          fileName,
          sha256: sha256(imagePath),
          sourceGroup: "real-material-test:note-a",
          decision: "pending-visual-review-and-authorization",
          trainingUse: "prohibited",
        },
      ],
    }),
    "utf8"
  );
  return { root, imagePath, intakePath };
}

function run(item: ReturnType<typeof fixture>, decision: "A" | "B" | "C") {
  const output = path.join(item.root, `authorized-${decision}.json`);
  const result = spawnSync(
    "python",
    [
      script,
      "--intake",
      item.intakePath,
      "--decision",
      decision,
      "--confirmed-by",
      "workspace-user",
      "--confirmation-note",
      `user selected ${decision}`,
      "--output",
      output,
    ],
    { encoding: "utf8" }
  );
  return { result, output };
}

test("real material authorization maps A/B/C without assigning review-pending images", () => {
  const expected = {
    A: {
      trainingUse: "permitted-after-visual-review-and-source-isolation",
      uses: ["commercial-model-training", "independent-release-test", "long-term-regression"],
    },
    B: {
      trainingUse: "prohibited",
      uses: ["independent-release-test", "long-term-regression"],
    },
    C: { trainingUse: "prohibited", uses: ["archive-only"] },
  } as const;

  for (const decision of ["A", "B", "C"] as const) {
    const item = fixture();
    const { result, output } = run(item, decision);
    assert.equal(result.status, 0, result.stderr);
    const document = JSON.parse(readFileSync(output, "utf8"));
    assert.equal(document.ok, true);
    assert.equal(document.authorization.decision, decision);
    assert.equal(document.authorization.trainingUse, expected[decision].trainingUse);
    assert.deepEqual(document.authorization.authorizedUses, expected[decision].uses);
    assert.equal(document.assignmentPolicy.sourceGroupAtomic, true);
    assert.equal(document.assignmentPolicy.trainingAndIndependentReleaseTestMutuallyExclusive, true);
    assert.equal(document.entries[0].trainingUse, "prohibited");
    assert.equal(document.entries[0].trainingEligibility, expected[decision].trainingUse);
    assert.equal(
      document.entries[0].decision,
      decision === "C" ? "archive-only" : "pending-original-resolution-visual-review-and-exclusive-assignment"
    );
  }
});

test("real material authorization rejects image drift and keeps the result invalid", () => {
  const item = fixture();
  writeFileSync(item.imagePath, "changed", "utf8");
  const { result, output } = run(item, "A");
  assert.notEqual(result.status, 0);
  const document = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(document.ok, false);
  assert.equal(document.status, "invalid");
  assert.match(document.errors.join("\n"), /sha256 drift/);
});
