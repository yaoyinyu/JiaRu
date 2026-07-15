import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const onePixelPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64"
);

test("audit-image-corpus reports valid images and exact duplicates", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "image-corpus-audit-"));
  const output = path.join(root, "report.json");
  await writeFile(path.join(root, "a.png"), onePixelPng);
  await writeFile(path.join(root, "b.png"), onePixelPng);

  await execFileAsync("python", [
    "model/training/audit-image-corpus.py",
    "--root", root,
    "--output", output,
  ], { cwd: path.resolve(".") });

  const report = JSON.parse(await readFile(output, "utf8")) as {
    ok: boolean;
    totals: { validImages: number; exactDuplicateGroups: number; exactDuplicateFiles: number };
    byTopLevelDirectory: Record<string, number>;
  };
  assert.equal(report.ok, true);
  assert.equal(report.totals.validImages, 2);
  assert.equal(report.totals.exactDuplicateGroups, 1);
  assert.equal(report.totals.exactDuplicateFiles, 1);
  assert.deepEqual(report.byTopLevelDirectory, { ".": 2 });
});
