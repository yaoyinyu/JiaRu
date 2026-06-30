import assert from "node:assert/strict";
import test from "node:test";
import {
  NAIL_TEXTURE_DATASET_VERSION,
  SOURCE_CSV_HEADERS,
  auditAnnotationDocument,
  buildDatasetSplit,
  buildInitialAnnotationDocument,
  createInitialPolygonFromCandidate,
  parseSourceRecords,
  stringifySourceRecords,
  toYoloSegmentationLines,
  upsertSourceRecord,
  type NailTextureAnnotationDocument,
} from "../src/lib/nail-texture-dataset.ts";

function sampleDocument(
  overrides?: Partial<NailTextureAnnotationDocument>
): NailTextureAnnotationDocument {
  return {
    version: NAIL_TEXTURE_DATASET_VERSION,
    image: {
      id: "sample-001",
      fileName: "sample-001.jpg",
      width: 100,
      height: 50,
      sourceGroup: "set-a",
      negative: false,
      ...overrides?.image,
    },
    annotations: overrides?.annotations ?? [
      {
        id: "n1",
        label: "nail_texture",
        polygon: [
          { x: 10, y: 10 },
          { x: 30, y: 10 },
          { x: 28, y: 28 },
          { x: 12, y: 30 },
        ],
        attributes: {
          fingerHint: "index",
          quality: 4,
        },
      },
    ],
    ...overrides,
  };
}

test("dataset annotation converts to yolo segmentation line", () => {
  const lines = toYoloSegmentationLines(sampleDocument());
  assert.equal(lines.length, 1);
  assert.equal(
    lines[0],
    "0 0.100000 0.200000 0.300000 0.200000 0.280000 0.560000 0.120000 0.600000"
  );
});

test("dataset audit accepts valid positive sample", () => {
  const result = auditAnnotationDocument(sampleDocument());
  assert.equal(result.ok, true);
  assert.equal(result.polygonCount, 1);
  assert.equal(result.issues.length, 0);
});

test("dataset audit rejects invalid polygons and negative sample violations", () => {
  const result = auditAnnotationDocument(
    sampleDocument({
      image: {
        id: "negative-001",
        fileName: "negative-001.jpg",
        width: 100,
        height: 50,
        negative: true,
      },
      annotations: [
        {
          id: "dup",
          label: "nail_texture",
          polygon: [
            { x: 10, y: 10 },
            { x: 110, y: 10 },
            { x: 10, y: 10 },
          ],
          attributes: {
            quality: 6,
          },
        },
        {
          id: "dup",
          label: "nail_texture",
          polygon: [
            { x: 0, y: 0 },
            { x: 0, y: 0 },
            { x: 0, y: 0 },
          ],
        },
      ],
    })
  );

  assert.equal(result.ok, false);
  assert.ok(result.issues.some((issue) => issue.code === "non_empty_negative_sample"));
  assert.ok(result.issues.some((issue) => issue.code === "duplicate_annotation_id"));
  assert.ok(result.issues.some((issue) => issue.code === "polygon_out_of_bounds"));
  assert.ok(result.issues.some((issue) => issue.code === "polygon_zero_area"));
  assert.ok(result.issues.some((issue) => issue.code === "invalid_quality"));
});

test("dataset split keeps same source group in one subset", () => {
  const split = buildDatasetSplit([
    sampleDocument({
      image: {
        id: "sample-a-1",
        fileName: "sample-a-1.jpg",
        width: 100,
        height: 50,
        sourceGroup: "merchant-a",
      },
    }),
    sampleDocument({
      image: {
        id: "sample-a-2",
        fileName: "sample-a-2.jpg",
        width: 100,
        height: 50,
        sourceGroup: "merchant-a",
      },
    }),
    sampleDocument({
      image: {
        id: "sample-b-1",
        fileName: "sample-b-1.jpg",
        width: 100,
        height: 50,
        sourceGroup: "merchant-b",
      },
    }),
  ]);

  const subsets = [split.train, split.val, split.test];
  const occurrences = subsets.filter(
    (subset) =>
      subset.includes("sample-a-1.jpg") || subset.includes("sample-a-2.jpg")
  );
  assert.equal(occurrences.length, 1);
  assert.deepEqual(
    occurrences[0].filter((fileName) => fileName.startsWith("sample-a-")),
    ["sample-a-1.jpg", "sample-a-2.jpg"]
  );
});

test("fallback candidate converts to initial polygon annotation document", () => {
  const polygon = createInitialPolygonFromCandidate({
    cx: 50,
    cy: 25,
    width: 20,
    length: 40,
    angle: 0,
  });
  assert.equal(polygon.length, 7);
  assert.ok(polygon.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)));

  const document = buildInitialAnnotationDocument(
    {
      id: "sample-seed",
      fileName: "sample-seed.jpg",
      width: 100,
      height: 50,
    },
    [
      {
        id: "fallback-1",
        cx: 50,
        cy: 25,
        width: 20,
        length: 40,
        angle: 0,
        score: 0.9,
        confidence: "high",
        source: "saliency",
        suggestedFinger: 1,
      },
    ],
    {
      sourceGroup: "seed-set",
    }
  );

  assert.equal(document.image.negative, false);
  assert.equal(document.image.sourceGroup, "seed-set");
  assert.equal(document.annotations.length, 1);
  assert.equal(document.annotations[0].attributes?.fingerHint, "index");
  assert.equal(document.annotations[0].attributes?.quality, 4);
});

test("sources csv can round-trip and upsert records", () => {
  const createdAt = "2026-06-30T00:00:00.000Z";
  const updatedAt = "2026-06-30T00:10:00.000Z";
  const csv = stringifySourceRecords([
    {
      imageId: "sample-001",
      fileName: "sample-001.jpg",
      sourceGroup: "seed-a",
      originType: "reference",
      originRef: "local",
      license: "internal-test",
      notes: "first",
      negative: false,
      annotationPath: "annotations/raw-json/sample-001.json",
      imagePath: "images/raw/sample-001.jpg",
      annotationCount: 4,
      createdAt,
      updatedAt,
    },
  ]);
  assert.match(csv, new RegExp(`^${SOURCE_CSV_HEADERS[0]}`, "m"));

  const parsed = parseSourceRecords(csv);
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].fileName, "sample-001.jpg");
  assert.equal(parsed[0].annotationCount, 4);

  const next = upsertSourceRecord(parsed, {
    ...parsed[0],
    notes: "updated",
    annotationCount: 5,
    createdAt: "2026-07-01T00:00:00.000Z",
    updatedAt: "2026-07-01T00:01:00.000Z",
  });
  assert.equal(next.length, 1);
  assert.equal(next[0].notes, "updated");
  assert.equal(next[0].annotationCount, 5);
  assert.equal(next[0].createdAt, createdAt);
});
