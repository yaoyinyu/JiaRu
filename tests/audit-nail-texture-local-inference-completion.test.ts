import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("completion audit reports external evidence blockers instead of false completion", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-completion-audit-"));
  const spec = path.join(root, "spec.md");
  const progress = path.join(root, "progress.md");
  const dataset = path.join(root, "dataset.json");
  const review = path.join(root, "review.json");
  const releaseTestSnapshot = path.join(root, "release-test-snapshot.json");
  const releaseTestQuality = path.join(root, "release-test-quality.json");
  const metrics = path.join(root, "metrics.json");
  const manifest = path.join(root, "manifest.json");
  const desktopPerformance = path.join(root, "desktop-performance.json");
  const desktopMemory = path.join(root, "desktop-memory.json");
  const output = path.join(root, "completion.json");
  await writeFile(spec, [
    "### 16.1 用户需要完成", "- [ ] 提供失败案例。", "### 16.2 工程侧需要完成",
    "- [x] 实现推理。", "- [ ] 建立真机报告。", "## 17. 推荐执行顺序",
  ].join("\n"));
  await writeFile(progress, "| `M1` | 工程 | ✅ PASS | tested |\n| `M3` | 真机 | 🟠 PARTIAL | desktop only |\n");
  await writeFile(dataset, JSON.stringify({ ok: true }));
  await writeFile(review, JSON.stringify({ dataset: { testImages: 13 } }));
  await writeFile(releaseTestSnapshot, JSON.stringify({
    snapshotId: "reviewed-candidate-v1",
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: 67, masks: 384, coreImages: 45, stressImages: 22 },
    representativeReleaseGate: { ok: false, actual: 67, required: 100, shortfall: 33 },
    itemsSha256: "a".repeat(64),
    items: Array.from({ length: 67 }, (_, index) => ({ fileName: `sample-${index}.jpg`, lane: "core", trainingUse: "prohibited" })),
  }));
  await writeFile(releaseTestQuality, JSON.stringify({
    ok: true,
    decision: "reject_v6_release_at_deployment_resolution",
    qualityGatePassed: false,
    trainingUse: "prohibited",
    snapshot: { itemsSha256: "a".repeat(64), counts: { images: 67, masks: 384 } },
    evaluations: { full512: { imgsz: 512, boxMap50: 0.837, maskMap50: 0.831, predictionLabels: 67 } },
  }));
  await writeFile(metrics, JSON.stringify({ box_map50: 0.86, seg_map50: 0.8 }));
  await writeFile(manifest, JSON.stringify({ modelFile: "missing.onnx" }));
  await writeFile(desktopPerformance, JSON.stringify({ ok: true, totals: { samples: 20 } }));
  await writeFile(desktopMemory, JSON.stringify({ ok: true, sampleCount: 20 }));

  const result = spawnSync("node", [
    "--no-warnings", "--experimental-strip-types", "scripts/audit-nail-texture-local-inference-completion.ts",
    "--spec", spec, "--progress", progress, "--dataset-readiness", dataset,
    "--candidate-review", review, "--best-metrics", metrics, "--production-manifest", manifest,
    "--release-test-snapshot", releaseTestSnapshot,
    "--release-test-quality", releaseTestQuality,
    "--desktop-performance", desktopPerformance, "--desktop-memory", desktopMemory,
    "--beta-review", path.join(root, "missing-beta.json"), "--failure-cases", path.join(root, "missing-failures.json"),
    "--mobile-report", `android=${path.join(root, "missing-android.json")}`,
    "--mobile-report", `android-tablet=${path.join(root, "missing-android-tablet.json")}`,
    "--mobile-report", `iphone=${path.join(root, "missing-iphone.json")}`,
    "--mobile-report", `ipad=${path.join(root, "missing-ipad.json")}`,
    "--output", output,
  ], { encoding: "utf8" });
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, false);
  assert.equal(report.decision, "hold");
  assert.equal(report.gates.bestCandidateMetrics.ok, false);
  assert.equal(report.gates.bestCandidateMetrics.evidenceScope, "frozen-reviewed-candidate-67-deployment-512");
  assert.equal(report.gates.desktopAcceptance.ok, true);
  assert.equal(report.gates.representativeReleaseTest.actual, 67);
  assert.equal(report.gates.representativeReleaseTest.evaluatedModelTestImages, 67);
  assert.equal(report.gates.representativeReleaseTest.historicalEvaluatedModelTestImages, 13);
  assert.equal(report.gates.representativeReleaseTest.evidenceScope, "frozen-reviewed-candidate");
  assert.deepEqual(report.blockingInputs.map((item: { code: string }) => item.code), [
    "USER_FAILURE_CASES", "MODEL_QUALITY_REGRESSION", "REPRESENTATIVE_RELEASE_TESTSET", "MOBILE_DEVICE_ACCEPTANCE", "USER_BETA_QUALITY_REVIEW",
  ]);
});
