import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("audit-screening-review summarizes coverage and warnings", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-screening-audit-"));
  const reviewDir = path.join(root, "review");
  await mkdir(reviewDir, { recursive: true });
  await writeFile(
    path.join(reviewDir, "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      "a.jpg,true,keep,good_detection,4,true,train,reference,light,red,highlight|gold_line,ok",
      "b.jpg,true,keep,good_detection,4,false,val,merchant,dark,black,glitter,ok",
      "c.jpg,true,keep,good_detection,5,false,test,negative,mixed,nude,cat_eye,ok",
      "",
    ].join("\n"),
    "utf8"
  );

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-screening-review.ts",
        "--root-dir",
        root,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 1) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    keptCount: number;
    sampleKinds: Record<string, number>;
    backgroundTones: Record<string, number>;
    effectTags: Record<string, number>;
    warnings: string[];
  };
  assert.equal(report.keptCount, 3);
  assert.equal(report.sampleKinds.reference, 1);
  assert.equal(report.sampleKinds.merchant, 1);
  assert.equal(report.sampleKinds.negative, 1);
  assert.equal(report.backgroundTones.light, 1);
  assert.equal(report.backgroundTones.dark, 1);
  assert.equal(report.effectTags.highlight, 1);
  assert.equal(report.effectTags.gold_line, 1);
  assert.ok(report.warnings.some((warning) => warning.includes("below the recommended first-batch target of 50")));

  const persisted = JSON.parse(
    await readFile(path.join(reviewDir, "screening-review-audit.json"), "utf8")
  ) as { keptCount: number };
  assert.equal(persisted.keptCount, 3);
});

test("audit-screening-review passes when coverage checks are satisfied", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-screening-audit-ok-"));
  const reviewDir = path.join(root, "review");
  await mkdir(reviewDir, { recursive: true });
  const rows = [
    "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
  ];
  for (let index = 1; index <= 50; index++) {
    const sampleKind =
      index <= 10 ? "negative" : index <= 20 ? "merchant" : "reference";
    const background = index % 2 === 0 ? "dark" : "light";
    const split = index <= 35 ? "train" : index <= 45 ? "val" : "test";
    const effect =
      index % 3 === 0 ? "highlight|gold_line" : index % 5 === 0 ? "cat_eye" : "glitter";
    rows.push(
      `sample-${index}.jpg,true,keep,good_detection,4,false,${split},${sampleKind},${background},red,${effect},ok`
    );
  }
  rows.push("");
  await writeFile(path.join(reviewDir, "screening-review.csv"), rows.join("\n"), "utf8");

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-screening-review.ts",
        "--root-dir",
        root,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 0);
});
