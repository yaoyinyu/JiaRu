import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDatasetSplit,
  type NailTextureAnnotationDocument,
} from "../src/lib/nail-texture-dataset.ts";

function documentFixture(fileName: string, sourceGroup: string): NailTextureAnnotationDocument {
  return {
    version: "nail-texture-annotation/v1",
    image: {
      id: fileName.replace(/\.[^.]+$/, ""),
      fileName,
      width: 1024,
      height: 1024,
      sourceGroup,
    },
    annotations: [
      {
        id: `${fileName}-nail-1`,
        label: "nail_texture",
        polygon: [
          { x: 10, y: 10 },
          { x: 20, y: 10 },
          { x: 20, y: 30 },
          { x: 10, y: 30 },
        ],
      },
    ],
    createdAt: "2026-07-04T00:00:00.000Z",
    updatedAt: "2026-07-04T00:00:00.000Z",
  };
}

test("buildDatasetSplit proportionally splits a single source batch", () => {
  const documents = Array.from({ length: 300 }, (_, index) =>
    documentFixture(`ai-${String(index).padStart(3, "0")}.png`, "ai-nail-2026-07-04")
  );

  const split = buildDatasetSplit(documents);

  assert.equal(split.train.length, 210);
  assert.equal(split.val.length, 45);
  assert.equal(split.test.length, 45);
  assert.equal(new Set([...split.train, ...split.val, ...split.test]).size, 300);
});

test("buildDatasetSplit keeps multiple source groups together", () => {
  const documents = [
    documentFixture("group-a-1.png", "group-a"),
    documentFixture("group-a-2.png", "group-a"),
    documentFixture("group-b-1.png", "group-b"),
    documentFixture("group-b-2.png", "group-b"),
  ];

  const split = buildDatasetSplit(documents);
  const buckets = [split.train, split.val, split.test];

  for (const group of [["group-a-1.png", "group-a-2.png"], ["group-b-1.png", "group-b-2.png"]]) {
    assert.ok(
      buckets.some((bucket) => group.every((fileName) => bucket.includes(fileName))),
      `expected ${group.join(",")} to stay in one split bucket`
    );
  }
});