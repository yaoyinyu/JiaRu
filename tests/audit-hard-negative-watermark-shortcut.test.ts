import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-hard-negative-watermark-shortcut.py");

test("watermark audit builds deterministic variants with multiple workers", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-watermark-audit-"));
  try {
    const first = path.join(root, "first.ppm");
    const second = path.join(root, "second.ppm");
    const pixels = Array.from({ length: 16 * 16 }, (_, index) =>
      index % 2 === 0 ? "255 64 32" : "32 96 255"
    ).join("\n");
    const ppm = `P3\n16 16\n255\n${pixels}\n`;
    await writeFile(first, ppm, "ascii");
    await writeFile(second, ppm.replace("255 64 32", "64 255 32"), "ascii");

    const python = String.raw`
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("watermark_audit", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
items = [
    {
        "imagePath": sys.argv[3],
        "fileName": "negative-b.ppm",
        "sourceFileName": "source-b.ppm",
        "imageSha256": module.sha256_file(Path(sys.argv[3])),
        "sourceGroup": "group-b",
    },
    {
        "imagePath": sys.argv[4],
        "fileName": "negative-a.ppm",
        "sourceFileName": "source-a.ppm",
        "imageSha256": module.sha256_file(Path(sys.argv[4])),
        "sourceGroup": "group-a",
    },
]
paths, records = module.build_variants(items, Path(sys.argv[2]), workers=2)
print(json.dumps({
    "records": [record["fileName"] for record in records],
    "pathCounts": {name: len(values) for name, values in paths.items()},
    "hashes": [
        record["variants"][variant]["sha256"]
        for record in records
        for variant in ("original", "crop12", "blur_corner")
    ],
}))
`;
    const output = execFileSync(
      "python",
      ["-c", python, script, path.join(root, "artifacts"), second, first],
      {
        encoding: "utf8",
        env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      }
    );
    const report = JSON.parse(output) as {
      records: string[];
      pathCounts: Record<string, number>;
      hashes: string[];
    };
    assert.deepEqual(report.records, ["negative-b.ppm", "negative-a.ppm"]);
    assert.deepEqual(report.pathCounts, {
      original: 2,
      crop12: 2,
      blur_corner: 2,
    });
    assert.equal(report.hashes.length, 6);
    assert.ok(report.hashes.every((value) => /^[a-f0-9]{64}$/.test(value)));
    assert.ok((await readFile(path.join(root, "artifacts", "variants", "crop12", "negative-001.png"))).length > 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
