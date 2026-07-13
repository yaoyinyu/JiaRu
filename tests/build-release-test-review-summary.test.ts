import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-release-test-review-summary.py");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "release-review-summary-"));
  const paths = Object.fromEntries(
    ["parent", "core", "stress-intake", "stress-review", "output"].map((name) => [
      name,
      path.join(root, `${name}.json`),
    ]),
  );
  writeFileSync(
    paths.parent,
    JSON.stringify({
      batchId: "release-v1",
      authorization: {
        authorizedUses: ["independent-release-test", "long-term-regression"],
        trainingUse: "prohibited",
      },
      entries: [
        { fileName: "core.jpg", sourceGroup: "group-core", decision: "core" },
        { fileName: "stress.jpg", sourceGroup: "group-stress", decision: "stress" },
      ],
    }),
  );
  writeFileSync(
    paths.core,
    JSON.stringify({
      ok: true,
      counts: { acceptedMasks: 5 },
      passFiles: ["core.jpg"],
      reworkFiles: [],
      excludeFiles: [],
    }),
  );
  writeFileSync(
    paths["stress-intake"],
    JSON.stringify({
      entries: [
        {
          fileName: "crop.png",
          parentFileName: "stress.jpg",
          sourceGroup: "derived-group",
          trainingUse: "prohibited",
        },
      ],
    }),
  );
  writeFileSync(
    paths["stress-review"],
    JSON.stringify({
      ok: true,
      counts: { acceptedMasks: 2 },
      passFiles: [],
      reworkFiles: ["crop.png"],
      excludeFiles: [],
    }),
  );
  return paths;
}

function args(paths: Record<string, string>) {
  return [
    script,
    "--parent-intake",
    paths.parent,
    "--core-review",
    paths.core,
    "--stress-intake",
    paths["stress-intake"],
    "--stress-review",
    paths["stress-review"],
    "--output",
    paths.output,
  ];
}

test("release-test review summary maps derived decisions back to parents", () => {
  const paths = fixture();
  execFileSync("python", args(paths));
  const report = JSON.parse(readFileSync(paths.output, "utf8"));
  assert.equal(report.ok, true);
  assert.deepEqual(report.counts, {
    parents: 2,
    pass: 1,
    rework: 1,
    excluded: 0,
    acceptedMasks: 7,
    acceptedSourceGroups: 1,
    upstreamExcluded: 0,
  });
  assert.equal(report.stressDerivedTrace[0].parentFileName, "stress.jpg");
});

test("release-test review summary rejects training-enabled derived regions", () => {
  const paths = fixture();
  const intake = JSON.parse(readFileSync(paths["stress-intake"], "utf8"));
  intake.entries[0].trainingUse = "allowed";
  writeFileSync(paths["stress-intake"], JSON.stringify(intake));
  const result = spawnSync("python", args(paths), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(paths.output, "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /permits training/);
});
