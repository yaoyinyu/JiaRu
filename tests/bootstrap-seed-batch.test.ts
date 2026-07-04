import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("bootstrap-seed-batch copies local images into a seed workspace and writes manifest", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-bootstrap-batch-"));
  const sourceDir = path.join(root, "source");
  const batchRoot = path.join(root, "seed-batch-001");
  await mkdir(sourceDir, { recursive: true });
  await writeFile(path.join(sourceDir, "a.jpg"), "a");
  await writeFile(path.join(sourceDir, "b.png"), "b");
  const fixtureDir = path.join(root, "fixtures");
  await mkdir(fixtureDir, { recursive: true });
  await writeFile(path.join(fixtureDir, "a.json"), JSON.stringify({ version: "nail-detection-fixture/v1", imagePath: "a.jpg", annotationPath: "b.png" }), "utf8");
  await writeFile(path.join(sourceDir, "ignore.txt"), "x");

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/bootstrap-seed-batch.ts",
        "--source-dir",
        sourceDir,
        "--root-dir",
        batchRoot,
        "--source-group",
        "seed-batch-001",
        "--origin-type",
        "web",
        "--default-origin-ref",
        "manual web sourcing 2026-07-01",
        "--fixture-dir",
        fixtureDir,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 0) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    copiedCount: number;
    manifestPath: string;
    fixturesDir: string;
    readmePath: string;
    fixtureCount: number;
    skippedAnnotationFiles: string[];
    screeningReviewPath: string;
  };
  assert.equal(report.copiedCount, 1);
  assert.equal(report.fixtureCount, 1);
  assert.deepEqual(report.skippedAnnotationFiles, ["b.png"]);
  assert.equal(path.basename(report.fixturesDir), "fixtures");

  const manifest = JSON.parse(await readFile(report.manifestPath, "utf8")) as {
    items: Array<{ fileName: string }>;
  };
  assert.deepEqual(
    manifest.items.map((item) => item.fileName),
    ["a.jpg"]
  );

  const readme = await readFile(report.readmePath, "utf8");
  assert.match(readme, /--fixture-dir/);
  assert.match(readme, /seed-batch-001\/fixtures/);

  const screeningCsv = await readFile(report.screeningReviewPath, "utf8");
  assert.match(screeningCsv, /backgroundTone/);
  assert.match(screeningCsv, /a\.jpg/);
});
