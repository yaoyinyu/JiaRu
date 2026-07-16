import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-sam-prompt-geometry.py");

function annotationDocument(annotationCount = 2) {
  const polygons = [
    [
      { x: 12, y: 12 },
      { x: 38, y: 12 },
      { x: 38, y: 38 },
      { x: 12, y: 38 },
    ],
    [
      { x: 62, y: 62 },
      { x: 88, y: 62 },
      { x: 88, y: 88 },
      { x: 62, y: 88 },
    ],
  ];
  return {
    version: "nail-texture-dataset/v1",
    image: {
      id: "sample",
      fileName: "sample.png",
      width: 100,
      height: 100,
      sourceGroup: "test-group",
      negative: false,
    },
    annotations: polygons.slice(0, annotationCount).map((polygon, index) => ({
      id: `n${index + 1}`,
      label: "nail_texture",
      polygon,
      attributes: {},
    })),
  };
}

async function fixture(annotationCount = 2) {
  const root = await mkdtemp(path.join(os.tmpdir(), "sam-geometry-audit-"));
  const annotationDir = path.join(root, "annotations");
  await mkdir(annotationDir, { recursive: true });
  const promptsPath = path.join(root, "prompts.json");
  const jsonOutput = path.join(root, "audit.json");
  const csvOutput = path.join(root, "audit.csv");
  await writeFile(
    promptsPath,
    JSON.stringify({
      images: [
        {
          fileName: "sample.png",
          sourceGroup: "test-group",
          boxes: [
            [0.1, 0.1, 0.4, 0.4],
            [0.6, 0.6, 0.9, 0.9],
          ],
        },
      ],
    }),
    "utf8"
  );
  await writeFile(
    path.join(annotationDir, "sample.json"),
    JSON.stringify(annotationDocument(annotationCount)),
    "utf8"
  );
  return { annotationDir, promptsPath, jsonOutput, csvOutput };
}

function args(paths: Awaited<ReturnType<typeof fixture>>) {
  return [
    script,
    "--prompts",
    paths.promptsPath,
    "--annotation-dir",
    paths.annotationDir,
    "--source",
    "unit-test",
    "--json-output",
    paths.jsonOutput,
    "--csv-output",
    paths.csvOutput,
  ];
}

test("SAM prompt geometry audit accepts aligned, separate polygons", async () => {
  const paths = await fixture();
  execFileSync("python", args(paths));

  const report = JSON.parse(await readFile(paths.jsonOutput, "utf8")) as {
    summary: Record<string, { pass: number; suspect: number; missing: number }>;
    rows: Array<{
      status: string;
      centerInside: boolean;
      maximumPeerBoundsIou: number;
      maximumPeerPolygonIntersectionArea: number;
    }>;
  };
  assert.deepEqual(report.summary["unit-test"], {
    pass: 2,
    suspect: 0,
    missing: 0,
  });
  assert.equal(report.rows.every((row) => row.status === "pass"), true);
  assert.equal(report.rows.every((row) => row.centerInside), true);
  assert.equal(report.rows.every((row) => row.maximumPeerBoundsIou === 0), true);
  assert.equal(
    report.rows.every((row) => row.maximumPeerPolygonIntersectionArea === 0),
    true
  );
  assert.match(await readFile(paths.csvOutput, "utf8"), /sample\.png,2,unit-test,pass/);
});

test("SAM prompt geometry audit reports a missing polygon and exits nonzero", async () => {
  const paths = await fixture(1);
  const result = spawnSync("python", args(paths), { encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr);

  const report = JSON.parse(await readFile(paths.jsonOutput, "utf8")) as {
    summary: Record<string, { pass: number; suspect: number; missing: number }>;
    rows: Array<{ status: string; reasons: string[] }>;
  };
  assert.deepEqual(report.summary["unit-test"], {
    pass: 1,
    suspect: 0,
    missing: 1,
  });
  assert.deepEqual(report.rows[1], {
    fileName: "sample.png",
    nailIndex: 2,
    source: "unit-test",
    status: "missing",
    reasons: ["annotation_polygon_missing"],
    areaRatio: null,
    boundsContainment: null,
    centerInside: null,
    bounds: null,
    maximumPeerBoundsIou: null,
    maximumPeerPolygonIntersectionArea: null,
  });
});

test("SAM prompt geometry audit does not reject separate slanted polygons only because their bounds overlap", async () => {
  const paths = await fixture();
  const document = annotationDocument();
  document.annotations[0].polygon = [
    { x: 10, y: 10 },
    { x: 90, y: 10 },
    { x: 10, y: 90 },
  ];
  document.annotations[1].polygon = [
    { x: 90, y: 90 },
    { x: 20, y: 90 },
    { x: 90, y: 20 },
  ];
  await writeFile(path.join(paths.annotationDir, "sample.json"), JSON.stringify(document), "utf8");
  await writeFile(
    paths.promptsPath,
    JSON.stringify({
      images: [
        {
          fileName: "sample.png",
          sourceGroup: "test-group",
          boxes: [
            [0.05, 0.05, 0.95, 0.95],
            [0.15, 0.15, 0.95, 0.95],
          ],
        },
      ],
    }),
    "utf8"
  );

  execFileSync("python", args(paths));
  const report = JSON.parse(await readFile(paths.jsonOutput, "utf8")) as {
    rows: Array<{
      status: string;
      maximumPeerBoundsIou: number;
      maximumPeerPolygonIntersectionArea: number;
    }>;
  };
  assert.equal(report.rows.every((row) => row.status === "pass"), true);
  assert.equal(report.rows.every((row) => row.maximumPeerBoundsIou > 0.35), true);
  assert.equal(
    report.rows.every((row) => row.maximumPeerPolygonIntersectionArea === 0),
    true
  );
});

test("SAM prompt geometry audit rejects polygons with real intersection area", async () => {
  const paths = await fixture();
  const document = annotationDocument();
  document.annotations[1].polygon = [
    { x: 30, y: 30 },
    { x: 60, y: 30 },
    { x: 60, y: 60 },
    { x: 30, y: 60 },
  ];
  await writeFile(path.join(paths.annotationDir, "sample.json"), JSON.stringify(document), "utf8");
  await writeFile(
    paths.promptsPath,
    JSON.stringify({
      images: [
        {
          fileName: "sample.png",
          sourceGroup: "test-group",
          boxes: [
            [0.1, 0.1, 0.4, 0.4],
            [0.25, 0.25, 0.65, 0.65],
          ],
        },
      ],
    }),
    "utf8"
  );

  execFileSync("python", args(paths));
  const report = JSON.parse(await readFile(paths.jsonOutput, "utf8")) as {
    rows: Array<{ status: string; reasons: string[]; maximumPeerPolygonIntersectionArea: number }>;
  };
  assert.equal(report.rows.every((row) => row.status === "suspect"), true);
  assert.equal(
    report.rows.every((row) =>
      row.reasons.includes("peer_polygon_intersection_area_above_maximum")
    ),
    true
  );
  assert.equal(report.rows.every((row) => row.maximumPeerPolygonIntersectionArea > 0), true);
});
