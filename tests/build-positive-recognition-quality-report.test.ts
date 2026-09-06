import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-positive-recognition-quality-report.py");
const ledgerScript = path.resolve("model/training/positive-release-consumption-ledger.py");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

function sha(value: string | Buffer | unknown): string {
  const payload = typeof value === "string" || Buffer.isBuffer(value) ? value : canonical(value);
  return createHash("sha256").update(payload).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "positive-recognition-"));
  const outputDir = path.join(root, "dataset");
  const artifactsDir = path.join(root, "artifacts");
  mkdirSync(path.join(outputDir, "labels", "test", "core"), { recursive: true });
  mkdirSync(path.join(artifactsDir, "labels"), { recursive: true });
  const polygon = "0 0.1 0.1 0.4 0.1 0.4 0.6 0.1 0.6";
  const prediction = `${polygon} 0.9\n`;
  const stems = Array.from({ length: 100 }, (_, index) => String.fromCharCode(97 + Math.floor(index / 26)) + String.fromCharCode(97 + (index % 26)));
  const items = stems.map((stem) => ({ fileName: `${stem}.jpg`, maskCount: 1, trainingUse: "prohibited" }));
  const snapshot = path.join(root, "snapshot.json");
  writeFileSync(snapshot, JSON.stringify({ trainingUse: "prohibited", itemsSha256: sha(items), items }));
  const records = stems.map((stem) => {
    const truthPath = path.join(outputDir, "labels", "test", "core", `${stem}.txt`);
    writeFileSync(truthPath, `${polygon}\n`);
    return { lane: "core", materializedFileName: `${stem}.jpg`, materializedLabel: `labels/test/core/${stem}.txt`, materializedLabelSha256: sha(readFileSync(truthPath)) };
  });
  const materialization = path.join(root, "materialization.json");
  writeFileSync(materialization, JSON.stringify({
    decision: "evaluation_only_frozen_reviewed_snapshot",
    trainingUse: "prohibited",
    sourceFrozenManifest: snapshot,
    sourceFrozenManifestSha256: sha(readFileSync(snapshot)),
    sourceItemsSha256: sha(items),
    outputDir,
    recordsSha256: sha(records),
    records,
  }));
  const predictionRecords = stems.map((stem) => {
    const predictionPath = path.join(artifactsDir, "labels", `${stem}.txt`);
    writeFileSync(predictionPath, prediction);
    return { stem, path: `labels/${stem}.txt`, sha256: sha(readFileSync(predictionPath)), prediction_count: 1 };
  });
  const artifactIndex = path.join(root, "artifacts.json");
  writeFileSync(artifactIndex, JSON.stringify({ split: "test", artifacts_dir: artifactsDir, prediction_records: predictionRecords, prediction_records_sha256: sha(predictionRecords) }));
  const weights = path.join(root, "best.pt");
  writeFileSync(weights, "weights");
  return { root, snapshot, materialization, artifactIndex, weights, artifactsDir };
}

test("逐实例正样本识别报告可构建并重放", () => {
  const value = fixture();
  const output = path.join(value.root, "report.json");
  execFileSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--output", output]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.schemaVersion, 2);
  assert.equal(report.ok, true);
  assert.equal(report.summary.weightedSpuriousRate, 0);
  assert.equal(report.summary.directlyExtractableImages, 100);
  execFileSync("python", [script, "--verify-report", output]);
});

test("复合运行时报告必须绑定选择锁并可重放", () => {
  const value = fixture();
  const runtimeLock = path.join(value.root, "runtime-lock.json");
  writeFileSync(runtimeLock, JSON.stringify({ candidate: "candidate57", fixed: true }));
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.runtime_selection_lock = runtimeLock;
  artifact.runtime_selection_lock_sha256 = sha(readFileSync(runtimeLock));
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const output = path.join(value.root, "composite-report.json");
  execFileSync("python", [
    script,
    "--snapshot-manifest", value.snapshot,
    "--materialization-report", value.materialization,
    "--artifact-index", value.artifactIndex,
    "--weights", value.weights,
    "--runtime-selection-lock", runtimeLock,
    "--score-threshold", "0.3",
    "--output", output,
  ]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.candidate.runtimeSelectionLock, runtimeLock);
  assert.equal(report.deploymentContract.selectionMode, "locked-composite-runtime");
  assert.equal(report.deploymentContract.scoreThreshold, 0.3);
  execFileSync("python", [script, "--verify-report", output]);

  artifact.runtime_selection_lock_sha256 = "0".repeat(64);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const rejected = spawnSync("python", [
    script,
    "--snapshot-manifest", value.snapshot,
    "--materialization-report", value.materialization,
    "--artifact-index", value.artifactIndex,
    "--weights", value.weights,
    "--runtime-selection-lock", runtimeLock,
    "--score-threshold", "0.3",
    "--output", path.join(value.root, "rejected.json"),
  ]);
  assert.equal(rejected.status, 2);
});

test("schema v3正式报告绑定releaseIdentity与一次性消费台账并可深度重放", () => {
  const value = fixture();
  const runtimeLock = path.join(value.root, "runtime-lock-v3.json");
  writeFileSync(runtimeLock, JSON.stringify({ candidate: "candidate58", fixed: true }));
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.runtime_selection_lock = runtimeLock;
  artifact.runtime_selection_lock_sha256 = sha(readFileSync(runtimeLock));
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const core = {
    candidateId: "candidate-58",
    runtimeSelectionLockSha256: sha(readFileSync(runtimeLock)),
    modelFiles: [{ role: "segment", sha256: sha(readFileSync(value.weights)) }],
    inputSize: 512,
    scoreThreshold: 0.5,
    combinationRulesSha256: "c".repeat(64),
    preprocessSha256: "d".repeat(64),
    postprocessSha256: "e".repeat(64),
  };
  const releaseIdentity = { core, coreSha256: sha(core), manifestSha256: "f".repeat(64) };
  const identityPath = path.join(value.root, "release-identity.json");
  const ledgerPath = path.join(value.root, "positive-consumption-ledger.json");
  writeFileSync(identityPath, JSON.stringify({ releaseIdentity }));
  const claimed = JSON.parse(execFileSync("python", [ledgerScript, "--action", "claim", "--ledger", ledgerPath, "--release-identity", identityPath, "--snapshot-manifest", value.snapshot, "--runtime-selection-lock", runtimeLock], { encoding: "utf8" }));
  execFileSync("python", [ledgerScript, "--action", "mark-read", "--ledger", ledgerPath, "--run-id", claimed.runId]);
  execFileSync("python", [ledgerScript, "--action", "mark-prediction", "--ledger", ledgerPath, "--run-id", claimed.runId]);
  execFileSync("python", [ledgerScript, "--action", "complete", "--ledger", ledgerPath, "--run-id", claimed.runId, "--artifact-index", value.artifactIndex]);
  const output = path.join(value.root, "schema-v3-report.json");
  execFileSync("python", [
    script,
    "--snapshot-manifest", value.snapshot,
    "--materialization-report", value.materialization,
    "--artifact-index", value.artifactIndex,
    "--weights", value.weights,
    "--runtime-selection-lock", runtimeLock,
    "--release-identity", identityPath,
    "--consumption-ledger", ledgerPath,
    "--score-threshold", "0.5",
    "--output", output,
  ]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.schemaVersion, 3);
  assert.deepEqual(report.releaseIdentity, releaseIdentity);
  assert.equal(report.inputs.consumptionLedgerSha256, sha(readFileSync(ledgerPath)));
  execFileSync("python", [script, "--verify-report", output]);
});

test("漏甲会让识别强门保持HOLD", () => {
  const value = fixture();
  const predictionPath = path.join(value.artifactsDir, "labels", "ab.txt");
  writeFileSync(predictionPath, "");
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.prediction_records[1].sha256 = sha(readFileSync(predictionPath));
  artifact.prediction_records[1].prediction_count = 0;
  artifact.prediction_records_sha256 = sha(artifact.prediction_records);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const output = path.join(value.root, "hold.json");
  const result = spawnSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--output", output]);
  assert.equal(result.status, 1);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.decision, "hold_positive_recognition_gate");
  assert.equal(report.summary.missing, 1);
  assert.equal(report.gates.everyImageHasModelOutput, false);
  const verify = spawnSync("python", [script, "--verify-report", output]);
  assert.equal(verify.status, 1);
});

test("拓扑无效预测按严重度计入加权门并HOLD", () => {
  const value = fixture();
  const predictionPath = path.join(value.artifactsDir, "labels", "ab.txt");
  writeFileSync(predictionPath, "0 0.1 0.1 0.4 0.6 0.1 0.6 0.4 0.1 0.9\n");
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.prediction_records[1].sha256 = sha(readFileSync(predictionPath));
  artifact.prediction_records_sha256 = sha(artifact.prediction_records);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const output = path.join(value.root, "invalid.json");
  const result = spawnSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--output", output]);
  assert.equal(result.status, 1);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.schemaVersion, 2);
  assert.equal(report.summary.invalidPredictionMasks, 1);
  assert.equal(report.gates.weightedSpuriousRate, false);
  assert.equal(report.summary.weightedSpuriousRate > 0, true);
  assert.equal(report.zeroDefectDiagnostics.zeroInvalidPredictionMasks, false);
});

test("预算内重复实例通过加权门且超预算HOLD", () => {
  const value = fixture();
  // 图a：正确预测 + 一个与真值 IoU≈0.2 的重复候选（低于匹配0.5、高于重复0.10）
  const predictionPath = path.join(value.artifactsDir, "labels", "aa.txt");
  writeFileSync(predictionPath, "0 0.1 0.1 0.4 0.1 0.4 0.6 0.1 0.6 0.9\n0 0.3 0.1 0.6 0.1 0.6 0.6 0.3 0.6 0.9\n");
  const artifact = JSON.parse(readFileSync(value.artifactIndex, "utf8"));
  artifact.prediction_records[0].sha256 = sha(readFileSync(predictionPath));
  artifact.prediction_records[0].prediction_count = 2;
  artifact.prediction_records_sha256 = sha(artifact.prediction_records);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const base = [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5"];
  const passOutput = path.join(value.root, "pass.json");
  execFileSync("python", [...base, "--output", passOutput]);
  const passed = JSON.parse(readFileSync(passOutput, "utf8"));
  assert.equal(passed.ok, true);
  assert.equal(passed.decision, "accept_positive_recognition_gate");
  assert.equal(passed.summary.duplicates, 1);
  assert.equal(passed.summary.weightedSpuriousRate, 0.01);
  assert.equal(passed.gates.weightedSpuriousRate, true);
  assert.equal(passed.zeroDefectDiagnostics.zeroDuplicates, false);
  const verifyPass = spawnSync("python", [script, "--verify-report", passOutput]);
  assert.equal(verifyPass.status, 0);
  writeFileSync(predictionPath, "0 0.1 0.1 0.4 0.1 0.4 0.6 0.1 0.6 0.9\n0 0.3 0.1 0.6 0.1 0.6 0.6 0.3 0.6 0.9\n0 0.31 0.1 0.61 0.1 0.61 0.6 0.31 0.6 0.9\n0 0.32 0.1 0.62 0.1 0.62 0.6 0.32 0.6 0.9\n");
  artifact.prediction_records[0].sha256 = sha(readFileSync(predictionPath));
  artifact.prediction_records[0].prediction_count = 4;
  artifact.prediction_records_sha256 = sha(artifact.prediction_records);
  writeFileSync(value.artifactIndex, JSON.stringify(artifact));
  const holdOutput = path.join(value.root, "hold.json");
  const held = spawnSync("python", [...base, "--output", holdOutput]);
  assert.equal(held.status, 1);
  const heldReport = JSON.parse(readFileSync(holdOutput, "utf8"));
  assert.equal(heldReport.gates.weightedSpuriousRate, false);
});

test("历史schema v1报告仍可按旧语义重放", () => {
  const value = fixture();
  const output = path.join(value.root, "legacy.json");
  const publicBuild = spawnSync("python", [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5", "--gate-mode", "zero-defect", "--output", output]);
  assert.equal(publicBuild.status, 2);
  const internalReplayBuilder = [
    "import argparse, importlib.util, json, pathlib, sys",
    "spec=importlib.util.spec_from_file_location('quality', sys.argv[1])",
    "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)",
    "args=argparse.Namespace(snapshot_manifest=sys.argv[2], materialization_report=sys.argv[3], artifact_index=sys.argv[4], weights=sys.argv[5], score_threshold=0.5, output=None, verify_report=None, min_images=100, min_instance_recall=0.90, min_complete_mask_ratio=0.85, max_missing_image_rate=0.10, gate_mode='zero-defect', max_weighted_spurious_rate=0.02)",
    "report=module.build(args, allow_legacy_replay=True)",
    "pathlib.Path(sys.argv[6]).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\\n', encoding='utf-8')",
  ].join("; ");
  execFileSync("python", ["-c", internalReplayBuilder, script, value.snapshot, value.materialization, value.artifactIndex, value.weights, output]);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.schemaVersion, 1);
  assert.equal(report.ok, true);
  assert.equal(report.gates.zeroDuplicates, true);
  assert.equal(report.gates.zeroFalsePositives, true);
  assert.equal(report.gates.zeroInvalidPredictionMasks, true);
  assert.equal(report.deploymentContract.zeroDuplicates, true);
  assert.equal(report.zeroDefectDiagnostics, undefined);
  const verify = spawnSync("python", [script, "--verify-report", output]);
  assert.equal(verify.status, 0);
});

test("正式质量门参数只能收紧不能放宽", () => {
  const value = fixture();
  const base = [script, "--snapshot-manifest", value.snapshot, "--materialization-report", value.materialization, "--artifact-index", value.artifactIndex, "--weights", value.weights, "--score-threshold", "0.5"];
  const cases = [
    ["--min-images", "99"],
    ["--min-instance-recall", "0.89"],
    ["--min-complete-mask-ratio", "0.84"],
    ["--max-missing-image-rate", "0.11"],
    ["--max-weighted-spurious-rate", "0.03"],
  ];
  for (const [flag, threshold] of cases) {
    const output = path.join(value.root, `${flag.slice(2)}.json`);
    const result = spawnSync("python", [...base, flag, threshold, "--output", output]);
    assert.equal(result.status, 2, `${flag}=${threshold} should be rejected`);
  }
  const validOutput = path.join(value.root, "valid.json");
  execFileSync("python", [...base, "--output", validOutput]);
  const tampered = JSON.parse(readFileSync(validOutput, "utf8"));
  tampered.deploymentContract.minimumImages = 99;
  const tamperedOutput = path.join(value.root, "tampered.json");
  writeFileSync(tamperedOutput, JSON.stringify(tampered));
  const replay = spawnSync("python", [script, "--verify-report", tamperedOutput]);
  assert.equal(replay.status, 2, "verification must reject a weakened self-reported contract");
});
