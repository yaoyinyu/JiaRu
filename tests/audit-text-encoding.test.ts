import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("audit-text-encoding accepts valid UTF-8 source and persists a report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-encoding-pass-"));
  const outputPath = path.join(root, "encoding-report.json");
  await mkdir(path.join(root, "nested"), { recursive: true });
  await writeFile(path.join(root, "正常.md"), "# 美甲纹理\n编码正常。\n", "utf8");
  await writeFile(path.join(root, "nested", "sample.ts"), 'export const message = "可用";\n', "utf8");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/audit-text-encoding.ts",
      "--root",
      root,
      "--output",
      outputPath,
    ],
    { cwd: path.resolve(".") }
  );
  const report = JSON.parse(stdout) as {
    ok: boolean;
    totals: { files: number; failures: number };
  };
  assert.equal(report.ok, true);
  assert.equal(report.totals.files, 2);
  assert.equal(report.totals.failures, 0);
  assert.equal(
    (JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean }).ok,
    true
  );
});

test("audit-text-encoding rejects invalid UTF-8, NUL, private-use, and mojibake text", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-encoding-fail-"));
  await writeFile(path.join(root, "invalid.md"), Buffer.from([0xff, 0xfe, 0xfd]));
  await writeFile(path.join(root, "nul.ts"), "before\0after", "utf8");
  await writeFile(
    path.join(root, "private.md"),
    `broken ${String.fromCodePoint(0xe123)} text`,
    "utf8"
  );
  await writeFile(
    path.join(root, "mojibake.md"),
    String.fromCodePoint(0x7efe, 0x572d, 0x608a),
    "utf8"
  );

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/audit-text-encoding.ts",
        "--root",
        root,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: unknown) => {
      const execError = error as Error & { stdout?: string };
      const report = JSON.parse(execError.stdout ?? "{}") as {
        ok: boolean;
        failures: Array<{ filePath: string; reasons: string[] }>;
      };
      assert.equal(report.ok, false);
      assert.ok(report.failures.some((item) => item.reasons.includes("invalid-utf8")));
      assert.ok(report.failures.some((item) => item.reasons.includes("nul-character")));
      assert.ok(report.failures.some((item) => item.reasons.includes("private-use-character")));
      assert.ok(report.failures.some((item) => item.reasons.includes("common-gbk-mojibake")));
      return true;
    }
  );
});
