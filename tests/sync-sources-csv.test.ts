import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import {
  NAIL_TEXTURE_DATASET_VERSION,
  parseSourceRecords,
} from "../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

test("sync sources csv rebuilds metadata from annotation documents", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-sync-sources-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });

  await writeFile(
    path.join(datasetRoot, "annotations", "raw-json", "sample-001.json"),
    JSON.stringify(
      {
        version: NAIL_TEXTURE_DATASET_VERSION,
        image: {
          id: "sample-001",
          fileName: "sample-001.jpg",
          width: 100,
          height: 50,
          sourceGroup: "merchant-a",
          negative: false,
        },
        annotations: [
          {
            id: "n1",
            label: "nail_texture",
            polygon: [
              { x: 10, y: 10 },
              { x: 30, y: 10 },
              { x: 30, y: 30 },
              { x: 10, y: 30 },
            ],
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", "model/training/sync-sources-csv.ts"],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const csv = await readFile(path.join(datasetRoot, "metadata", "sources.csv"), "utf8");
  const records = parseSourceRecords(csv);
  assert.equal(records.length, 1);
  assert.equal(records[0].imageId, "sample-001");
  assert.equal(records[0].sourceGroup, "merchant-a");
  assert.equal(records[0].annotationCount, 1);
  assert.equal(records[0].originType, "other");
});
