import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-release-test-annotation-review.py");

test("release-test annotation review layers a repair report over the original candidate report", () => {
  const root = mkdtempSync(path.join(tmpdir(), "release-annotation-review-"));
  const annotations = path.join(root, "annotations");
  mkdirSync(annotations);
  const intake = path.join(root, "intake.json");
  const originalReport = path.join(root, "original.json");
  const repairReport = path.join(root, "repair.json");
  const review = path.join(root, "review.json");
  const output = path.join(root, "output.json");
  writeFileSync(
    intake,
    JSON.stringify({
      batchId: "release-v1",
      counts: { stress: 0 },
      entries: [
        { fileName: "a.jpg", decision: "core", sourceGroup: "group-a" },
        { fileName: "b.jpg", decision: "core", sourceGroup: "group-b" },
      ],
    }),
  );
  writeFileSync(
    originalReport,
    JSON.stringify({
      outputs: [
        { fileName: "a.jpg", polygonCount: 2, sourceGroup: "group-a" },
        { fileName: "b.jpg", polygonCount: 3, sourceGroup: "group-b" },
      ],
    }),
  );
  writeFileSync(
    repairReport,
    JSON.stringify({
      outputs: [{ fileName: "b.jpg", polygonCount: 1, sourceGroup: "group-b" }],
    }),
  );
  writeFileSync(
    review,
    JSON.stringify({
      passFiles: ["a.jpg", "b.jpg"],
      excludeFiles: [],
      reviewPolicy: { candidateOnlyUntilHumanReview: true },
      repairBatches: ["repair-v2"],
    }),
  );
  for (const [fileName, sourceGroup, count] of [
    ["a.jpg", "group-a", 2],
    ["b.jpg", "group-b", 1],
  ] as const) {
    writeFileSync(
      path.join(annotations, `${path.parse(fileName).name}.json`),
      JSON.stringify({
        image: { fileName, sourceGroup },
        annotations: Array.from({ length: count }, () => ({
          polygon: [
            { x: 0, y: 0 },
            { x: 1, y: 0 },
            { x: 1, y: 1 },
          ],
        })),
      }),
    );
  }

  execFileSync("python", [
    script,
    "--intake",
    intake,
    "--candidate-report",
    originalReport,
    "--candidate-report",
    repairReport,
    "--review",
    review,
    "--annotations",
    annotations,
    "--output",
    output,
  ]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.acceptedMasks, 3);
  assert.equal(report.candidateReportPaths.length, 2);
  assert.deepEqual(report.repairBatches, ["repair-v2"]);
});
