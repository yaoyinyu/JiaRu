import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-release-test-region-intake.py");

function sha256(data: Buffer) {
  return createHash("sha256").update(data).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "release-region-intake-"));
  const regionDir = path.join(root, "regions");
  mkdirSync(regionDir);
  const parentBytes = Buffer.from("parent-image");
  const regionBytes = Buffer.from("derived-region");
  writeFileSync(path.join(regionDir, "crop.png"), regionBytes);
  const parentIntake = path.join(root, "parent.json");
  const report = path.join(root, "regions.json");
  const output = path.join(root, "output.json");
  writeFileSync(
    parentIntake,
    JSON.stringify({
      batchId: "release-v1",
      authorization: {
        authorizedUses: ["independent-release-test", "long-term-regression"],
        trainingUse: "prohibited",
      },
      entries: [
        {
          fileName: "parent.jpg",
          sha256: sha256(parentBytes),
          sourceGroup: "parent-group",
          decision: "stress",
        },
      ],
    }),
  );
  writeFileSync(
    report,
    JSON.stringify({
      ok: true,
      outputs: [
        {
          parentFileName: "parent.jpg",
          parentSha256: sha256(parentBytes),
          outputFileName: "crop.png",
          outputSha256: sha256(regionBytes),
          sourceGroup: "derived-group",
          regionId: "primary",
          normalizedBox: [0, 0, 1, 1],
        },
      ],
    }),
  );
  return { root, regionDir, parentIntake, report, output };
}

test("release-test region intake preserves parent provenance and prohibits training", () => {
  const item = fixture();
  execFileSync("python", [
    script,
    "--parent-intake",
    item.parentIntake,
    "--region-report",
    item.report,
    "--region-dir",
    item.regionDir,
    "--output",
    item.output,
  ]);
  const document = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(document.ok, true);
  assert.equal(document.entries[0].parentFileName, "parent.jpg");
  assert.equal(document.entries[0].trainingUse, "prohibited");
  assert.equal(document.entries[0].sourceGroup, "derived-group");
});

test("release-test region intake rejects a non-stress parent", () => {
  const item = fixture();
  const parent = JSON.parse(readFileSync(item.parentIntake, "utf8"));
  parent.entries[0].decision = "core";
  writeFileSync(item.parentIntake, JSON.stringify(parent));
  const result = spawnSync(
    "python",
    [
      script,
      "--parent-intake",
      item.parentIntake,
      "--region-report",
      item.report,
      "--region-dir",
      item.regionDir,
      "--output",
      item.output,
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(result.status, 0);
  const document = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(document.ok, false);
  assert.match(document.errors.join("\n"), /not a stress item/);
});
