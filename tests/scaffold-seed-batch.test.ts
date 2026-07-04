import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("scaffold-seed-batch creates workspace directories and manifest template", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-seed-scaffold-"));
  const batchRoot = path.join(root, "seed-batch-001");

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/scaffold-seed-batch.ts",
        "--root-dir",
        batchRoot,
        "--source-group",
        "seed-batch-001",
        "--origin-type",
        "web",
        "--default-origin-ref",
        "manual web sourcing 2026-07-01",
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

  const result = JSON.parse(stdout) as {
    ok: boolean;
    imagesDir: string;
    debugDir: string;
    fixturesDir: string;
    reviewDir: string;
    manifestPath: string;
    readmePath: string;
    screeningReviewPath: string;
    failureClassificationPath: string;
  };
  assert.equal(result.ok, true);
  assert.equal(path.basename(result.fixturesDir), "fixtures");

  const manifest = JSON.parse(await readFile(result.manifestPath, "utf8")) as {
    sourceGroup: string;
    originType: string;
    license: string;
    defaultOriginRef: string;
    items: Array<{ fileName: string }>;
  };
  assert.equal(manifest.sourceGroup, "seed-batch-001");
  assert.equal(manifest.originType, "web");
  assert.equal(manifest.license, "internal-test-only");
  assert.equal(manifest.defaultOriginRef, "manual web sourcing 2026-07-01");
  assert.deepEqual(manifest.items.map((item) => item.fileName), ["sample-001.jpg"]);

  const readme = await readFile(result.readmePath, "utf8");
  assert.match(readme, /batch-verify-nail-detection/);
  assert.match(readme, /--fixture-dir/);
  assert.match(readme, /fixtures\/: optional green-circle/);
  assert.match(readme, /build-reviewed-intake-batch/);
  assert.match(readme, /run-phase1-intake-pipeline/);
  assert.match(readme, /screening-review\.csv/);
  assert.match(readme, /failure-classification\.csv/);

  const screeningCsv = await readFile(result.screeningReviewPath, "utf8");
  assert.match(screeningCsv, /keepForTraining/);
  assert.match(screeningCsv, /targetSplitHint/);
  assert.match(screeningCsv, /backgroundTone/);
  assert.match(screeningCsv, /effectTags/);

  const failureCsv = await readFile(result.failureClassificationPath, "utf8");
  assert.match(failureCsv, /category/);
  assert.match(failureCsv, /postprocess|data|model|ui/);
});
