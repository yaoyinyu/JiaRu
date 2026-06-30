import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import test from "node:test";
import { NAIL_TEXTURE_DATASET_VERSION } from "../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

function sampleAnnotation(fileName: string, sourceGroup: string) {
  return {
    version: NAIL_TEXTURE_DATASET_VERSION,
    image: {
      id: fileName.replace(/\.[^.]+$/, ""),
      fileName,
      width: 100,
      height: 50,
      sourceGroup,
      negative: false,
    },
    annotations: [
      {
        id: "n1",
        label: "nail_texture",
        polygon: [
          { x: 10, y: 10 },
          { x: 28, y: 8 },
          { x: 30, y: 26 },
          { x: 12, y: 28 },
        ],
        attributes: {
          quality: 4,
          fingerHint: "index",
        },
      },
    ],
  };
}

async function runScript(scriptPath: string, datasetRoot: string) {
  await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", scriptPath],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );
}

test("training scripts generate split, audit csv, and yolo labels", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-texture-dataset-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });

  await writeFile(
    path.join(datasetRoot, "annotations", "raw-json", "sample-001.json"),
    JSON.stringify(sampleAnnotation("sample-001.jpg", "merchant-a"), null, 2),
    "utf8"
  );
  await writeFile(
    path.join(datasetRoot, "annotations", "raw-json", "sample-002.json"),
    JSON.stringify(sampleAnnotation("sample-002.jpg", "merchant-b"), null, 2),
    "utf8"
  );

  await runScript("model/training/split-dataset.ts", datasetRoot);
  await runScript("model/training/audit-labels.ts", datasetRoot);
  await runScript("model/training/convert-annotations.ts", datasetRoot);

  const split = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "split.json"), "utf8")
  ) as { train: string[]; val: string[]; test: string[] };
  assert.equal(
    split.train.length + split.val.length + split.test.length,
    2
  );

  const auditCsv = await readFile(
    path.join(datasetRoot, "metadata", "label-audit.csv"),
    "utf8"
  );
  assert.match(auditCsv, /sample-001\.json/);
  assert.match(auditCsv, /sample-002\.json/);

  const splitEntries = [
    ...split.train.map((fileName) => ["train", fileName] as const),
    ...split.val.map((fileName) => ["val", fileName] as const),
    ...split.test.map((fileName) => ["test", fileName] as const),
  ];
  assert.equal(splitEntries.length, 2);

  for (const [subset, fileName] of splitEntries) {
    const labelPath = path.join(
      datasetRoot,
      "labels-yolo-seg",
      subset,
      fileName.replace(/\.[^.]+$/, ".txt")
    );
    const contents = await readFile(labelPath, "utf8");
    assert.match(contents, /^0 /);
  }
});
