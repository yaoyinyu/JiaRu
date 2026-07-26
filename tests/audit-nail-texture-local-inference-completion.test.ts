import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { link, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  INSTANCE_REVIEW_HEADER,
  REQUIRED_SCENARIO_DIMENSIONS,
  SCENARIO_REGRESSION_HEADER,
} from "../scripts/lib/nail-texture-release-product-quality.ts";
import {
  createApprovedHardNegativeEvidence,
  createProtectedRoleEvidence,
  writePatternTestPng,
} from "./helpers/hard-negative-evidence.ts";
import { createFormalThresholdEvidence } from "./helpers/formal-threshold-evidence.ts";

function run(
  script: string,
  args: string[],
  environment: NodeJS.ProcessEnv = {},
) {
  return spawnSync(
    "node",
    ["--no-warnings", "--experimental-strip-types", script, ...args],
    {
      encoding: "utf8",
      env: { ...process.env, ...environment },
    },
  );
}

async function writeJson(filePath: string, value: unknown) {
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function canonicalSha256(value: unknown): string {
  return createHash("sha256").update(canonical(value), "utf8").digest("hex");
}

function buildProductQuality(snapshot: string, instances: string, scenarios: string, output: string) {
  const result = run("scripts/build-nail-texture-release-product-quality.ts", [
    "--snapshot", snapshot,
    "--instances-csv", instances,
    "--scenarios-csv", scenarios,
    "--reviewer", "product-owner",
    "--output", output,
  ]);
  assert.equal(result.status, 0, `${result.stderr}\n${result.stdout}`);
}

async function buildFrozenReleaseTestQuality(
  root: string,
  snapshot: string,
  output: string,
  counts: { images: number; masks: number; coreImages: number; stressImages: number; parentSourceGroups: number },
) {
  const evaluationRoot = path.join(root, "frozen-evaluation");
  const materialization = path.join(root, "frozen-materialization.json");
  await writeJson(materialization, {
    ok: true,
    trainingUse: "prohibited",
    outputDir: evaluationRoot,
    counts,
    sourceIsolation: { parentSourceGroupOverlap: [], exactImageHashOverlap: [] },
  });
  const weights = path.join(root, "quality-candidate.pt");
  await writeFile(weights, Buffer.from("quality-candidate-weights"));
  const writeMetric = async (
    label: string,
    imgsz: number,
    predictions: number,
    boxMap50: number,
    maskMap50: number,
    datasetRoot = evaluationRoot,
  ) => {
    const artifact = path.join(root, `${label}-artifacts.json`);
    await writeJson(artifact, { split: "test", counts: { prediction_labels: predictions } });
    const metric = path.join(root, `${label}-metrics.json`);
    await writeJson(metric, {
      split: "test",
      imgsz,
      dataset_root: datasetRoot,
      weights,
      box_map50: boxMap50,
      seg_map50: maskMap50,
      box_map: boxMap50 - 0.3,
      seg_map: maskMap50 - 0.3,
      evaluation_artifacts: { index: artifact, counts: { prediction_labels: predictions } },
    });
    return metric;
  };
  const baseline = await writeMetric("quality-baseline", 512, 13, 0.9, 0.85, path.join(root, "historical-test"));
  const full512 = await writeMetric("quality-full-512", 512, counts.images, 0.895, 0.845);
  const full640 = await writeMetric("quality-full-640", 640, counts.images, 0.9, 0.85);
  const core512 = await writeMetric("quality-core-512", 512, counts.coreImages, 0.9, 0.85);
  const stress512 = await writeMetric("quality-stress-512", 512, counts.stressImages, 0.885, 0.835);
  const assessment = path.join(root, "quality-assessment.json");
  await writeJson(assessment, {
    ok: true,
    baseline: { metricsPath: baseline, metrics: { boxMap50: 0.9, maskMap50: 0.85 } },
    thresholds: { maxBoxMap50Drop: 0.02, maxMaskMap50Drop: 0.02, minBoxMap50: 0.85, minMaskMap50: 0.75 },
    candidates: [
      { label: `release${counts.images}`, metricsPath: full512, metrics: { boxMap50: 0.895, maskMap50: 0.845, boxMap50To95: 0.595, maskMap50To95: 0.545 }, qualityGatePassed: true },
      { label: `core${counts.coreImages}`, metricsPath: core512, metrics: { boxMap50: 0.9, maskMap50: 0.85, boxMap50To95: 0.6, maskMap50To95: 0.55 }, qualityGatePassed: true },
      { label: `stress${counts.stressImages}`, metricsPath: stress512, metrics: { boxMap50: 0.885, maskMap50: 0.835, boxMap50To95: 0.585, maskMap50To95: 0.535 }, qualityGatePassed: true },
    ],
  });
  const result = spawnSync("python", [
    path.resolve("model/training/build-frozen-release-test-quality-report.py"),
    "--snapshot-manifest", snapshot,
    "--materialization-report", materialization,
    "--baseline-metrics", baseline,
    "--full-512", full512,
    "--full-640", full640,
    "--core-512", core512,
    "--stress-512", stress512,
    "--assessment", assessment,
    "--output", output,
  ], { encoding: "utf8" });
  assert.equal(result.status, 0, `${result.stderr}\n${result.stdout}`);
}

async function writeReleaseManifest(root: string, manifestPath: string, version: string, modelBytes: Buffer) {
  const modelPath = path.join(root, `${version}.onnx`);
  await writeFile(modelPath, modelBytes);
  await writeJson(manifestPath, {
    version,
    inputSize: 512,
    task: "segment",
    backendPreferences: ["webgpu", "wasm"],
    modelFile: path.basename(modelPath),
    modelSizeBytes: modelBytes.length,
    sha256: createHash("sha256").update(modelBytes).digest("hex"),
    labels: ["nail_texture"],
  });
  return modelPath;
}

function registerRelease(manifestPath: string, registryPath: string) {
  const result = run("scripts/register-model-release.ts", [
    "--manifest", manifestPath,
    "--registry", registryPath,
  ]);
  assert.equal(result.status, 0, result.stderr);
}

function writeRollbackAudit(registryPath: string, manifestPath: string, outputPath: string) {
  const result = run("scripts/audit-release-rollback.ts", [
    "--registry", registryPath,
    "--manifest", manifestPath,
    "--output", outputPath,
  ]);
  assert.equal(result.status, 0, `${result.stderr}\n${result.stdout}`);
}

async function prepareDeviceReport(root: string, deviceFamily: string) {
  const deviceRoot = path.join(root, deviceFamily);
  await mkdir(deviceRoot);
  const sessionId = `${deviceFamily}-session`;
  const rawPerformance = path.join(deviceRoot, "raw-performance.json");
  const performance = path.join(deviceRoot, "performance.json");
  const rawMemory = path.join(deviceRoot, "raw-memory.json");
  const memory = path.join(deviceRoot, "memory.json");
  const output = path.join(deviceRoot, "acceptance.json");
  await writeJson(rawPerformance, {
    version: "nail-texture-device-session/v1",
    sessionId,
    deviceFamily,
    samples: Array.from({ length: 20 }, (_, index) => ({
      imageId: `sample-${index + 1}`,
      sessionId,
      deviceFamily,
      backend: "model",
      backendName: "wasm",
      modelVersion: "nail-texture-seg-v2",
      inputSize: 512,
      elapsedMs: 700 + index,
      workerElapsedMs: 650 + index,
    })),
  });
  const performanceResult = run("scripts/verify-recognition-performance.ts", [
    "--profile", "mobile", "--min-samples", "20", "--output", performance, rawPerformance,
  ]);
  assert.equal(performanceResult.status, 0, performanceResult.stderr);
  const memorySamples = Array.from({ length: 20 }, (_, index) => ({
    iteration: index + 1,
    usedJSHeapBytes: 20 * 1024 * 1024 + (index % 3) * 1024,
    browserPrivateBytes: 120 * 1024 * 1024 + (index % 3) * 1024,
    browserWorkingSetBytes: 100 * 1024 * 1024,
    browserProcessCount: 1,
  }));
  await writeJson(rawMemory, {
    version: "nail-texture-recognition-memory/v1",
    profile: deviceFamily,
    sessionId,
    deviceFamily,
    backend: "wasm",
    modelVersion: "nail-texture-seg-v2",
    inputSize: 512,
    sampleCount: 20,
    samples: memorySamples,
  });
  const memoryResult = run("scripts/verify-recognition-memory.ts", ["--input", rawMemory, "--output", memory]);
  assert.equal(memoryResult.status, 0, memoryResult.stderr);
  const acceptanceResult = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", deviceFamily,
    "--device-name", `${deviceFamily} fixture`,
    "--os", "fixture-os",
    "--browser", "fixture-browser",
    "--backend", "wasm",
    "--performance", performance,
    "--memory", memory,
    "--output", output,
  ]);
  assert.equal(acceptanceResult.status, 0, acceptanceResult.stderr);
  return output;
}

async function prepareHardNegativeAudit(
  root: string,
  output: string,
  registerExternalRoot?: (externalRoot: string) => void,
) {
  const python = process.env.PYTHON ?? "python";
  const recorder = path.resolve(
    "model/training/record-independent-hard-negative-authorization.py",
  );
  const workspaceBuilder = path.resolve(
    "model/training/build-independent-hard-negative-review-workspace.py",
  );
  const reviewFinalizer = path.resolve(
    "model/training/finalize-independent-hard-negative-review.py",
  );
  const holdoutFinalizer = path.resolve(
    "model/training/finalize-reviewed-independent-hard-negative-holdout.py",
  );
  const audit = path.resolve(
    "model/training/audit-hard-negative-watermark-shortcut.py",
  );
  const runPython = (args: string[], environment: NodeJS.ProcessEnv = {}) =>
    spawnSync(python, args, {
      encoding: "utf8",
      env: { ...process.env, ...environment },
    });
  const shaFile = async (filePath: string) =>
    createHash("sha256").update(await readFile(filePath)).digest("hex");

  const images = path.join(root, "independent-hard-negative-images");
  const threshold = createFormalThresholdEvidence(0.45);
  registerExternalRoot?.(threshold.root);
  const userAuthorization = path.join(root, "independent-user-authorization.json");
  const confirmationNote =
    "用户明确允许该精确测试批次用于独立发布测试和长期回归。";
  await writeJson(userAuthorization, {
    schemaVersion: 1,
    ok: true,
    decision: "authorized_for_independent_holdout_evaluation",
    confirmedBy: "workspace-user",
    confirmationNote,
    authorizationEvidence: {
      kind: "codex-user-message",
      threadId: "019f4ca0-a894-7b63-8ec9-c286885a5a22",
      decisionId:
        "goal-thread/019f4ca0-a894-7b63-8ec9-c286885a5a22/completion-audit-fixture",
      userMessageText: confirmationNote,
      userMessageSha256: createHash("sha256")
        .update(confirmationNote)
        .digest("hex"),
    },
    sourceRoot: images,
    scopeIncludesDescendants: false,
    authorizedUses: [
      "independent-release-test",
      "long-term-regression",
      "model-diagnostic-evaluation",
      "data-quality-review",
    ],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
    trainingUse: "prohibited-for-independent-holdout",
  });

  const sources: Array<{
    fileName: string;
    sourceGroup: string;
    imageSha256: string;
    imagePath: string;
  }> = [];
  for (let index = 0; index < 100; index += 1) {
    const sequence = 161 + index;
    const family = `completion_family_${String(index % 20).padStart(2, "0")}`;
    const variant = String((index % 99) + 1).padStart(2, "0");
    const fileName =
      `hard_negative_independent_20260724_${String(sequence).padStart(3, "0")}_` +
      `${family}_${variant}.png`;
    const imagePath = path.join(images, fileName);
    writePatternTestPng(imagePath, sequence);
    sources.push({
      fileName,
      sourceGroup: `fixture:${family}`,
      imageSha256: await shaFile(imagePath),
      imagePath,
    });
  }

  const frozen = runPython([
    recorder,
    "--source-root", images,
    "--user-authorization", userAuthorization,
    "--candidate-weights", threshold.weights,
    "--candidate-threshold-report", threshold.thresholdReport,
    "--batch-date", "20260724",
    "--sequence-start", "161",
    "--sequence-end", "260",
  ]);
  assert.equal(frozen.status, 0, frozen.stderr);
  const freezeRoot = path.join(images, "_independent_holdout_freeze_v1");
  const freezeManifest = path.join(freezeRoot, "freeze-manifest-v1.json");
  const authorization = path.join(freezeRoot, "authorization-record-A-v1.json");
  const machineAudit = path.join(freezeRoot, "machine-audit-v1.json");

  const protectedRoles = createProtectedRoleEvidence(root);
  const workspace = path.join(root, "independent-review-workspace");
  const built = runPython([
    workspaceBuilder,
    "--authorization", authorization,
    "--machine-audit", machineAudit,
    "--freeze-manifest", freezeManifest,
    "--train-index", protectedRoles.train,
    "--val-index", protectedRoles.val,
    "--frozen-test-manifest", protectedRoles.frozenTest,
    "--output-dir", workspace,
  ]);
  assert.equal(built.status, 0, built.stderr);

  const decisionTemplate = await readFile(
    path.join(workspace, "review-decisions-v1.csv"),
    "utf8",
  );
  const completedDecisions = path.join(root, "review-decisions-completed.csv");
  const completedLines = decisionTemplate
    .replace(/^\uFEFF/, "")
    .trimEnd()
    .split(/\r?\n/)
    .map((line, index) => {
      if (index === 0) return line;
      const fields = line.split(",");
      assert.equal(fields.length, 9);
      fields[6] = "pass";
      fields[7] = "";
      fields[8] =
        "Original-resolution review confirms a clear complete non-human deployment hard negative.";
      return fields.join(",");
    });
  await writeFile(
    completedDecisions,
    `\uFEFF${completedLines.join("\n")}\n`,
    "utf8",
  );

  const reviewed = path.join(root, "independent-reviewed");
  const finalizedReview = runPython([
    reviewFinalizer,
    "--workspace", path.join(workspace, "review-workspace-v1.json"),
    "--decisions", completedDecisions,
    "--output-dir", reviewed,
  ]);
  assert.equal(finalizedReview.status, 0, finalizedReview.stderr);
  const candidateManifest = path.join(
    reviewed,
    "hard-negative-candidate-manifest-v1.json",
  );
  const approvedHoldout = path.join(
    reviewed,
    "approved-independent-hard-negative-holdout-v1.json",
  );
  const finalizedHoldout = runPython([
    holdoutFinalizer,
    "--candidate-manifest", candidateManifest,
    "--output", approvedHoldout,
  ]);
  assert.equal(finalizedHoldout.status, 0, finalizedHoldout.stderr);

  const fakePythonRoot = path.join(root, "fake-python");
  const fakeUltralytics = path.join(fakePythonRoot, "ultralytics");
  await mkdir(fakeUltralytics, { recursive: true });
  await writeFile(
    path.join(fakeUltralytics, "__init__.py"),
    [
      "class _Tensor:",
      "    def detach(self): return self",
      "    def cpu(self): return self",
      "    def tolist(self): return []",
      "",
      "class _Boxes:",
      "    conf = _Tensor()",
      "    def __len__(self): return 0",
      "",
      "class _Result:",
      "    boxes = _Boxes()",
      "",
      "class YOLO:",
      "    def __init__(self, weights): self.weights = weights",
      "    def predict(self, source, **kwargs): return [_Result() for _ in source]",
      "",
    ].join("\n"),
    "utf8",
  );
  const pythonEnvironment = {
    PYTHONPATH: [fakePythonRoot, process.env.PYTHONPATH]
      .filter(Boolean)
      .join(path.delimiter),
  };
  const artifacts = path.join(root, "independent-hard-negative-artifacts");
  const audited = runPython(
    [
      audit,
      "--weights", threshold.weights,
      "--hard-negative-manifest", approvedHoldout,
      "--output", output,
      "--artifacts-dir", artifacts,
      "--dataset-role", "independent-holdout",
      "--deployment-confidence", "0.45",
    ],
    pythonEnvironment,
  );
  assert.equal(audited.status, 0, audited.stderr);

  const trainingEvidence = createApprovedHardNegativeEvidence(root, sources);
  const trainingAudit = path.join(root, "training-hard-negative-audit.json");
  const trainingAudited = runPython(
    [
      audit,
      "--weights", threshold.weights,
      "--hard-negative-manifest", trainingEvidence.approvedManifest,
      "--output", trainingAudit,
      "--artifacts-dir", path.join(root, "training-hard-negative-artifacts"),
      "--dataset-role", "training",
      "--deployment-confidence", "0.45",
    ],
    pythonEnvironment,
  );
  assert.equal(trainingAudited.status, 0, trainingAudited.stderr);
  return { pythonEnvironment, trainingAudit };
}

async function preparePassingFixture(
  root: string,
  registerExternalRoot?: (externalRoot: string) => void,
) {
  const files = {
    spec: path.join(root, "spec.md"),
    progress: path.join(root, "progress.md"),
    dataset: path.join(root, "dataset.json"),
    review: path.join(root, "review.json"),
    snapshot: path.join(root, "release-test-snapshot.json"),
    quality: path.join(root, "release-test-quality.json"),
    hardNegative: path.join(root, "hard-negative-watermark-audit.json"),
    metrics: path.join(root, "metrics.json"),
    manifest: path.join(root, "manifest.json"),
    desktopPerformance: path.join(root, "desktop-performance.json"),
    desktopMemory: path.join(root, "desktop-memory.json"),
    beta: path.join(root, "beta.json"),
    failures: path.join(root, "failures.json"),
    productQuality: path.join(root, "release-product-quality.json"),
    productInstances: path.join(root, "release-product-instances.csv"),
    productScenarios: path.join(root, "release-product-scenarios.csv"),
    registry: path.join(root, "release-registry.json"),
    rollback: path.join(root, "rollback.json"),
  };
  await writeFile(files.spec, [
    "### 16.1 用户需要完成", "- [x] 用户证据完成。", "### 16.2 工程侧需要完成",
    "- [x] 工程证据完成。", "## 17. 推荐执行顺序",
  ].join("\n"), "utf8");
  await writeFile(files.progress, "| `M1` | 工程 | ✅ PASS | tested |\n", "utf8");
  await writeJson(files.dataset, { ok: true });
  await writeJson(files.review, { dataset: { testImages: 100 } });
  const snapshotItems = Array.from({ length: 100 }, (_, index) => ({
    fileName: `sample-${index}.jpg`,
    lane: index < 70 ? "core" : "stress",
    sourceGroup: `release-source-${index}`,
    parentSourceGroup: `release-parent-${index % 20}`,
    imageSha256: createHash("sha256").update(`release-image-${index}`).digest("hex"),
    annotationSha256: createHash("sha256").update(`release-annotation-${index}`).digest("hex"),
    maskCount: 5,
    trainingUse: "prohibited",
  }));
  const itemsSha256 = canonicalSha256(snapshotItems);
  const snapshot = {
    snapshotId: "reviewed-candidate-v2",
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: 100, masks: 500, coreImages: 70, stressImages: 30, parentSourceGroups: 20 },
    representativeReleaseGate: { ok: true, actual: 100, required: 100, shortfall: 0 },
    itemsSha256,
    items: snapshotItems,
  };
  await writeJson(files.snapshot, snapshot);
  await buildFrozenReleaseTestQuality(root, files.snapshot, files.quality, snapshot.counts);
  const hardNegativeFixture = await prepareHardNegativeAudit(
    root,
    files.hardNegative,
    registerExternalRoot,
  );
  await writeJson(files.metrics, { box_map50: 0.9, seg_map50: 0.85 });
  const previousModelBytes = Buffer.alloc(1024, 0x31);
  const previousModelPath = await writeReleaseManifest(root, files.manifest, "nail-texture-seg-v1", previousModelBytes);
  registerRelease(files.manifest, files.registry);
  const currentModelBytes = Buffer.alloc(2048, 0x32);
  const currentModelPath = await writeReleaseManifest(
    root,
    files.manifest,
    "nail-texture-seg-v2",
    currentModelBytes,
  );
  registerRelease(files.manifest, files.registry);
  await writeJson(files.desktopPerformance, { ok: true, totals: { samples: 20 } });
  await writeJson(files.desktopMemory, { ok: true, sampleCount: 20 });
  await writeJson(files.beta, {
    version: "nail-texture-beta-quality-review/v1",
    ok: true,
    reviewedByUser: true,
    sampleCount: 100,
    directlyUsableRate: 0.85,
  });
  await writeJson(files.failures, { version: "nail-texture-user-failure-cases/v1", ok: true, sampleCount: 4 });
  const instanceRows = [[...INSTANCE_REVIEW_HEADER].join(",")];
  for (const item of snapshotItems) {
    for (let instanceIndex = 1; instanceIndex <= item.maskCount; instanceIndex += 1) {
      instanceRows.push(`${item.fileName},${item.sourceGroup},${item.imageSha256},${instanceIndex},directly_usable,false,false,100,2,100,5`);
    }
  }
  await writeFile(files.productInstances, `${instanceRows.join("\n")}\n`, "utf8");
  await writeFile(files.productScenarios, [
    [...SCENARIO_REGRESSION_HEADER].join(","),
    ...REQUIRED_SCENARIO_DIMENSIONS.map((dimension) => `${dimension},${dimension}-coverage,100,0.90,0.89,0.90,0.88`),
  ].join("\n") + "\n", "utf8");
  buildProductQuality(files.snapshot, files.productInstances, files.productScenarios, files.productQuality);
  const productQuality = JSON.parse(await readFile(files.productQuality, "utf8"));
  writeRollbackAudit(files.registry, files.manifest, files.rollback);
  const rollback = JSON.parse(await readFile(files.rollback, "utf8"));
  const devices: Record<string, string> = {};
  for (const device of ["android", "android-tablet", "iphone", "ipad"]) {
    devices[device] = await prepareDeviceReport(root, device);
  }
  return {
    files,
    productQuality,
    rollback,
    snapshot,
    devices,
    previousModelPath,
    currentModelPath,
    currentModelBytes,
    hardNegativePythonEnvironment: hardNegativeFixture.pythonEnvironment,
    trainingHardNegativeAudit: hardNegativeFixture.trainingAudit,
  };
}

async function captureSharedEvidenceBaseline(
  fixture: Awaited<ReturnType<typeof preparePassingFixture>>,
) {
  const registryPath = fixture.files.registry;
  const productQuality = structuredClone(fixture.productQuality);
  const hardNegative = JSON.parse(
    await readFile(fixture.files.hardNegative, "utf8"),
  );
  const mutableVariantPath = hardNegative.records[0].variants.original.path;
  const evidencePaths = [
    ...new Set([
      ...Object.values(fixture.files),
      ...Object.values(fixture.devices),
      fixture.previousModelPath,
      fixture.currentModelPath,
      mutableVariantPath,
    ]),
  ];
  const evidence = new Map(
    await Promise.all(
      evidencePaths.map(async (filePath) => [
        filePath,
        await readFile(filePath),
      ] as const),
    ),
  );

  return async () => {
    fixture.files.registry = registryPath;
    fixture.productQuality = structuredClone(productQuality);
    await Promise.all(
      [...evidence].map(([filePath, contents]) =>
        writeFile(filePath, contents)
      ),
    );
  };
}

function runAudit(
  fixture: Awaited<ReturnType<typeof preparePassingFixture>>,
  output: string,
) {
  const { files, devices } = fixture;
  return run("scripts/audit-nail-texture-local-inference-completion.ts", [
    "--spec", files.spec,
    "--progress", files.progress,
    "--dataset-readiness", files.dataset,
    "--candidate-review", files.review,
    "--release-test-snapshot", files.snapshot,
    "--release-test-quality", files.quality,
    "--hard-negative-audit", files.hardNegative,
    "--best-metrics", files.metrics,
    "--production-manifest", files.manifest,
    "--desktop-performance", files.desktopPerformance,
    "--desktop-memory", files.desktopMemory,
    "--beta-review", files.beta,
    "--failure-cases", files.failures,
    "--release-product-quality", files.productQuality,
    "--release-registry", files.registry,
    "--rollback-audit", files.rollback,
    ...Object.entries(devices).flatMap(([device, filePath]) => ["--mobile-report", `${device}=${filePath}`]),
    "--output", output,
  ], fixture.hardNegativePythonEnvironment);
}

async function readReport(output: string) {
  return JSON.parse(await readFile(output, "utf8"));
}

test("completion audit v2 rejects forged, drifted, weak, and incomplete evidence", async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-completion-audit-v2-"));
  const externalRoots = new Set<string>();
  t.after(async () => {
    await Promise.all(
      [root, ...externalRoots].map((temporaryRoot) =>
        rm(temporaryRoot, { recursive: true, force: true })
      ),
    );
  });
  const fixture = await preparePassingFixture(
    root,
    (externalRoot) => externalRoots.add(externalRoot),
  );
  const restoreSharedEvidence = await captureSharedEvidenceBaseline(fixture);
  t.afterEach(restoreSharedEvidence);

  // This synthetic bound fixture validates evidence binding and replay mechanics.
  // It does not attest a real user identity or exercise real Ultralytics inference.
  await t.test("accepts a fully bound synthetic release evidence fixture", async () => {
    const output = path.join(root, "complete.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 0, result.stderr);
    const report = await readReport(output);
    assert.equal(report.ok, true);
    assert.equal(report.decision, "complete");
    assert.equal(report.version, "nail-texture-local-inference-completion-audit/v2");
    assert.equal(report.summary.gateCount, 14);
    assert.equal(report.gates.independentHardNegativeWatermark.ok, true);
    assert.equal(report.gates.releaseProductQuality.ok, true);
    assert.equal(report.gates.releaseRollback.ok, true);
  });

  await t.test("rejects training negatives even when their watermark audit is stable", async () => {
    const original = await readFile(fixture.files.hardNegative);
    await writeFile(
      fixture.files.hardNegative,
      await readFile(fixture.trainingHardNegativeAudit),
    );
    const output = path.join(root, "training-negative-audit.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.independentHardNegativeWatermark.ok, false);
    assert.equal(report.gates.independentHardNegativeWatermark.evidence.deepVerificationOk, true);
    assert.ok(report.blockingInputs.some(
      (item: { code: string }) => item.code === "INDEPENDENT_HARD_NEGATIVE_WATERMARK_AUDIT",
    ));
    await writeFile(fixture.files.hardNegative, original);
  });

  await t.test("rejects forged hard-negative decisions and drifted variant evidence", async () => {
    const original = JSON.parse(await readFile(fixture.files.hardNegative, "utf8"));
    const forged = structuredClone(original);
    forged.deploymentThreshold.crop12.counts[0] = 1;
    await writeJson(fixture.files.hardNegative, forged);
    let output = path.join(root, "forged-hard-negative-audit.json");
    let result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    let report = await readReport(output);
    assert.equal(report.gates.independentHardNegativeWatermark.evidence.deepVerificationOk, false);
    assert.match(report.gates.independentHardNegativeWatermark.errors.join(" "), /deep verification failed/);

    await writeJson(fixture.files.hardNegative, original);
    const variantPath = original.records[0].variants.original.path as string;
    const originalVariant = await readFile(variantPath);
    await writeFile(variantPath, Buffer.from("drifted"));
    output = path.join(root, "drifted-hard-negative-audit.json");
    result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    report = await readReport(output);
    assert.equal(report.gates.independentHardNegativeWatermark.evidence.deepVerificationOk, false);
    await writeFile(variantPath, originalVariant);
  });

  await t.test("rejects a handwritten frozen quality PASS or decision drift", async () => {
    const original = JSON.parse(await readFile(fixture.files.quality, "utf8"));
    await writeJson(fixture.files.quality, {
      ...original,
      qualityGatePassed: false,
      decision: "reject_candidate_release_at_deployment_resolution",
    });
    const output = path.join(root, "forged-frozen-quality.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.bestCandidateMetrics.qualityReportDeepVerificationOk, false);
    assert.match(report.gates.bestCandidateMetrics.qualityReportVerificationErrors.join(" "), /deep replay failed/);
    await writeJson(fixture.files.quality, original);
  });

  await t.test("protects frozen quality transitive evidence from audit output overwrite", async () => {
    const quality = JSON.parse(await readFile(fixture.files.quality, "utf8"));
    const metricPath = quality.inputs.full_512 as string;
    const before = await readFile(metricPath);
    const result = runAudit(fixture, metricPath);
    assert.notEqual(result.status, 0);
    assert.deepEqual(await readFile(metricPath), before);
  });

  await t.test("treats a non-PASS progress marker as a formal blocking gate", async () => {
    await writeFile(fixture.files.progress, "| `M1` | 工程 | 🟠 PARTIAL | incomplete |\n", "utf8");
    const output = path.join(root, "partial-marker.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.progressMarkers.ok, false);
    assert.equal(report.summary.failedGates, 1);
    assert.deepEqual(report.gates.progressMarkers.incompleteMarkers.map((item: { id: string }) => item.id), ["M1"]);
    assert.ok(report.blockingInputs.some((item: { code: string }) => item.code === "INCOMPLETE_PROGRESS_MARKERS"));
    await writeFile(fixture.files.progress, "| `M1` | 工程 | ✅ PASS | tested |\n", "utf8");
  });

  await t.test("rejects an empty progress table instead of vacuously passing it", async () => {
    await writeFile(fixture.files.progress, "# progress\n", "utf8");
    const output = path.join(root, "empty-progress.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.progressMarkers.ok, false);
    assert.equal(report.gates.progressMarkers.markerCount, 0);
    assert.match(
      report.blockingInputs.find((item: { code: string }) => item.code === "INCOMPLETE_PROGRESS_MARKERS")?.summary ?? "",
      /no parseable markers/,
    );
    await writeFile(fixture.files.progress, "| `M1` | 工程 | ✅ PASS | tested |\n", "utf8");
  });

  await t.test("rejects missing checklist sections instead of treating empty arrays as complete", async () => {
    const original = await readFile(fixture.files.spec, "utf8");
    await writeFile(fixture.files.spec, "# incomplete specification\n", "utf8");
    const output = path.join(root, "missing-checklists.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.userChecklist.ok, false);
    assert.equal(report.gates.engineeringChecklist.ok, false);
    assert.equal(report.gates.userChecklist.items.length, 0);
    assert.equal(report.gates.engineeringChecklist.items.length, 0);
    assert.ok(report.blockingInputs.some((item: { code: string }) => item.code === "SPEC_USER_CHECKLIST"));
    assert.ok(report.blockingInputs.some((item: { code: string }) => item.code === "SPEC_ENGINEERING_CHECKLIST"));
    await writeFile(fixture.files.spec, original, "utf8");
  });

  await t.test("rejects malformed and duplicate checklist rows", async () => {
    const original = await readFile(fixture.files.spec, "utf8");
    await writeFile(fixture.files.spec, [
      "# specification preamble",
      "",
      "### 16.1 用户需要完成",
      "- [x] 用户证据完成。",
      "- [ ]缺少复选框后的空格",
      "### 16.2 工程侧需要完成",
      "- [x] 重复工程证据。",
      "- [x] 重复工程证据。",
      "## 17. 推荐执行顺序",
    ].join("\n"), "utf8");
    const output = path.join(root, "malformed-duplicate-checklists.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.userChecklist.ok, false);
    assert.deepEqual(report.gates.userChecklist.malformedRows, [{
      lineNumber: 5,
      text: "- [ ]缺少复选框后的空格",
    }]);
    assert.equal(report.gates.engineeringChecklist.ok, false);
    assert.deepEqual(report.gates.engineeringChecklist.duplicateItems, ["重复工程证据。"]);
    assert.match(
      report.blockingInputs.find((item: { code: string }) => item.code === "SPEC_USER_CHECKLIST")?.summary ?? "",
      /malformed user checklist rows.*5/i,
    );
    assert.match(
      report.blockingInputs.find((item: { code: string }) => item.code === "SPEC_ENGINEERING_CHECKLIST")?.summary ?? "",
      /duplicate engineering checklist items.*重复工程证据/i,
    );
    await writeFile(fixture.files.spec, original, "utf8");
  });

  await t.test("rejects a malformed marker row that would otherwise disappear from the audit", async () => {
    await writeFile(
      fixture.files.progress,
      "| `M1` | 工程 | ✅ PASS | tested |\n| `M2` | 工程 | ✅ PASS | missing final separator\n",
      "utf8",
    );
    const output = path.join(root, "malformed-progress.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.progressMarkers.ok, false);
    assert.equal(report.gates.progressMarkers.markerCount, 1);
    assert.deepEqual(report.gates.progressMarkers.malformedRows, [{
      lineNumber: 2,
      text: "| `M2` | 工程 | ✅ PASS | missing final separator",
    }]);
    assert.match(
      report.blockingInputs.find((item: { code: string }) => item.code === "INCOMPLETE_PROGRESS_MARKERS")?.summary ?? "",
      /Malformed progress marker rows.*2/,
    );
    await writeFile(fixture.files.progress, "| `M1` | 工程 | ✅ PASS | tested |\n", "utf8");
  });

  await t.test("rejects duplicate PASS marker IDs instead of counting both", async () => {
    await writeFile(
      fixture.files.progress,
      "| `M1` | 工程一 | ✅ PASS | tested once |\n| `M1` | 工程二 | ✅ PASS | tested twice |\n",
      "utf8",
    );
    const output = path.join(root, "duplicate-progress.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.progressMarkers.ok, false);
    assert.equal(report.gates.progressMarkers.markerCount, 2);
    assert.equal(report.gates.progressMarkers.uniqueMarkerCount, 1);
    assert.deepEqual(report.gates.progressMarkers.duplicateMarkerIds, ["M1"]);
    assert.match(
      report.blockingInputs.find((item: { code: string }) => item.code === "INCOMPLETE_PROGRESS_MARKERS")?.summary ?? "",
      /Duplicate progress marker IDs.*M1/,
    );
    await writeFile(fixture.files.progress, "| `M1` | 工程 | ✅ PASS | tested |\n", "utf8");
  });

  await t.test("rejects forged outer product-quality PASS and snapshot drift", async () => {
    await writeJson(fixture.files.productQuality, { ...fixture.productQuality, errors: ["hidden failure"] });
    let output = path.join(root, "forged-product-quality.json");
    let result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    let report = await readReport(output);
    assert.equal(report.gates.releaseProductQuality.ok, false);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /errors must be empty|does not match replay/);

    await writeJson(fixture.files.productQuality, {
      ...fixture.productQuality,
      snapshot: { itemsSha256: "b".repeat(64) },
    });
    output = path.join(root, "snapshot-drift.json");
    result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    report = await readReport(output);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /missing snapshot\.path|snapshot.*does not match replay/);
    await writeJson(fixture.files.productQuality, fixture.productQuality);
  });

  await t.test("rejects a fully handwritten product-quality PASS without raw evidence", async () => {
    await writeJson(fixture.files.productQuality, {
      version: "nail-texture-release-product-quality/v1",
      ok: true,
      decision: "pass",
      reviewedByUser: true,
      reviewer: "forged-reviewer",
      trainingUse: "prohibited",
      sampleImages: 100,
      sampleInstances: 500,
      directlyUsableRate: 1,
      contaminationInstanceRate: 0,
      roughRectangleRate: 0,
      pixelLeakageRate: 0,
      missingRate: 0,
      frozenMaximumMissingRate: 0.1,
      minimumAllowedDelta: -0.02,
      scenarioGroups: fixture.productQuality.scenarioGroups,
      errors: [],
    });
    const output = path.join(root, "fully-forged-product-quality.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseProductQuality.ok, false);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /missing snapshot\.path|missing rawEvidence/);
    await writeJson(fixture.files.productQuality, fixture.productQuality);
  });

  await t.test("rejects product-quality evidence after the instance CSV drifts", async () => {
    const original = await readFile(fixture.files.productInstances, "utf8");
    await writeFile(fixture.files.productInstances, original.replace(",100,2,100,5", ",100,3,100,5"), "utf8");
    const output = path.join(root, "product-instance-csv-drift.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseProductQuality.ok, false);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /rawEvidence|pixelLeakageRate/);
    await writeFile(fixture.files.productInstances, original, "utf8");
  });

  await t.test("rejects product-quality evidence after the expected snapshot drifts", async () => {
    const original = await readFile(fixture.files.snapshot, "utf8");
    const drifted = JSON.parse(original);
    drifted.snapshotId = "drifted-after-product-report";
    await writeJson(fixture.files.snapshot, drifted);
    const output = path.join(root, "product-snapshot-source-drift.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseProductQuality.ok, false);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /snapshot.*does not match replay/);
    await writeFile(fixture.files.snapshot, original, "utf8");
  });

  await t.test("rejects a recomputed snapshot that reuses one image SHA under different names", async () => {
    const original = await readFile(fixture.files.snapshot, "utf8");
    const duplicateHashSnapshot = JSON.parse(original);
    duplicateHashSnapshot.items[1].imageSha256 = duplicateHashSnapshot.items[0].imageSha256;
    duplicateHashSnapshot.itemsSha256 = canonicalSha256(duplicateHashSnapshot.items);
    await writeJson(fixture.files.snapshot, duplicateHashSnapshot);
    const output = path.join(root, "product-snapshot-duplicate-image-hash.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.representativeReleaseTest.snapshotOk, false);
    assert.equal(report.gates.releaseProductQuality.ok, false);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /duplicate imageSha256/);
    await writeFile(fixture.files.snapshot, original, "utf8");
  });

  await t.test("rejects rebinding to another internally valid snapshot path", async () => {
    const alternateSnapshot = path.join(root, "alternate-valid-release-test-snapshot.json");
    await writeFile(alternateSnapshot, await readFile(fixture.files.snapshot));
    buildProductQuality(
      alternateSnapshot,
      fixture.files.productInstances,
      fixture.files.productScenarios,
      fixture.files.productQuality,
    );
    const output = path.join(root, "alternate-snapshot-rebind.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseProductQuality.ok, false);
    assert.match(report.gates.releaseProductQuality.errors.join(" "), /snapshot\.path does not match expected frozen snapshot/);
    buildProductQuality(
      fixture.files.snapshot,
      fixture.files.productInstances,
      fixture.files.productScenarios,
      fixture.files.productQuality,
    );
    fixture.productQuality = JSON.parse(await readFile(fixture.files.productQuality, "utf8"));
  });

  await t.test("protects direct and transitive evidence files from --output overwrite", async (overwriteTest) => {
    const manifestAlias = path.join(root, "production-manifest-hardlink-alias.json");
    await link(fixture.files.manifest, manifestAlias);
    const cases = [
      ["production manifest", fixture.files.manifest],
      ["existing hardlink alias", manifestAlias],
      ["product instance CSV", fixture.files.productInstances],
      ["rollback candidate model", fixture.previousModelPath],
    ] as const;
    for (const [label, protectedPath] of cases) {
      await overwriteTest.test(label, async () => {
        const before = await readFile(protectedPath);
        const result = runAudit(fixture, protectedPath);
        assert.equal(result.status, 1);
        assert.match(result.stderr, /must not overwrite an input evidence file/);
        assert.deepEqual(await readFile(protectedPath), before);
      });
    }
  });

  const weakCases: Array<[string, Record<string, unknown>, RegExp]> = [
    ["directly-usable", { directlyUsableRate: 0.849 }, /directlyUsableRate/],
    ["contamination", { contaminationInstanceRate: 0.1 }, /contaminationInstanceRate/],
    ["rough-rectangle", { roughRectangleRate: 0.151 }, /roughRectangleRate/],
    ["pixel-leakage", { pixelLeakageRate: -0.001 }, /pixelLeakageRate/],
    ["missing-rate", { missingRate: 0.11 }, /missingRate does not match replay/],
    ["self-relaxed-missing-ceiling", { frozenMaximumMissingRate: 1 }, /frozenMaximumMissingRate does not match replay/],
    ["self-relaxed-regression-floor", { minimumAllowedDelta: -0.5 }, /minimumAllowedDelta does not match replay/],
    ["snapshot-image-count", { sampleImages: 99 }, /sampleImages/],
    ["snapshot-instance-count", { sampleInstances: 499 }, /sampleInstances/],
    ["scenario-ok", {
      scenarioGroups: [{ name: "stress", dimension: "skin-tone", sampleCount: 100, ok: false, boxMap50Delta: -0.01, maskMap50Delta: -0.01 }],
    }, /scenarioGroups does not match replay/],
    ["scenario-delta", {
      scenarioGroups: [{ name: "stress", dimension: "skin-tone", sampleCount: 100, ok: true, boxMap50Delta: -0.021, maskMap50Delta: -0.02 }],
    }, /scenarioGroups does not match replay/],
    ["scenario-missing-dimension", {
      scenarioGroups: fixture.productQuality.scenarioGroups.filter((group) => group.dimension !== "device-backend"),
    }, /scenarioGroups does not match replay/],
  ];
  for (const [name, mutation, expected] of weakCases) {
    await t.test(`rejects ${name} threshold or scenario evidence`, async () => {
      await writeJson(fixture.files.productQuality, { ...fixture.productQuality, ...mutation });
      const output = path.join(root, `${name}.json`);
      const result = runAudit(fixture, output);
      assert.equal(result.status, 1);
      const report = await readReport(output);
      assert.equal(report.gates.releaseProductQuality.ok, false);
      assert.match(report.gates.releaseProductQuality.errors.join(" "), expected);
      await writeJson(fixture.files.productQuality, fixture.productQuality);
    });
  }

  await t.test("rejects forged rollback PASS without verified release integrity", async () => {
    await writeJson(fixture.files.rollback, {
      ...fixture.rollback,
      releases: fixture.rollback.releases.map((release, index) => index === 0 ? { ...release, integrityOk: false } : release),
    });
    const output = path.join(root, "forged-rollback.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseRollback.ok, false);
    assert.match(report.gates.releaseRollback.errors.join(" "), /differs from current-state replay/);
    assert.ok(report.blockingInputs.some((item: { code: string }) => item.code === "RELEASE_ROLLBACK_AUDIT"));
    await writeJson(fixture.files.rollback, fixture.rollback);
  });

  await t.test("rejects a fully hand-written rollback PASS when its bound registry does not exist", async () => {
    const realRegistryPath = fixture.files.registry;
    const missingRegistryPath = path.join(root, "missing-release-registry.json");
    fixture.files.registry = missingRegistryPath;
    await writeJson(fixture.files.rollback, {
      ...fixture.rollback,
      inputs: {
        ...fixture.rollback.inputs,
        registry: { path: missingRegistryPath, sha256: "a".repeat(64) },
      },
      ok: true,
      decision: "approved_release_rollback_audit",
      releases: fixture.rollback.releases.map((release) => ({
        ...release,
        ok: true,
        integrityOk: true,
        errors: [],
      })),
      errors: [],
    });
    const output = path.join(root, "fully-forged-rollback.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseRollback.ok, false);
    assert.match(report.gates.releaseRollback.errors.join(" "), /cannot replay rollback evidence/);
    fixture.files.registry = realRegistryPath;
    await writeJson(fixture.files.rollback, fixture.rollback);
  });

  await t.test("rejects rollback evidence after the current model drifts", async () => {
    await writeFile(fixture.currentModelPath, Buffer.from("drifted-after-rollback-report"));
    const output = path.join(root, "rollback-model-drift.json");
    const result = runAudit(fixture, output);
    assert.equal(result.status, 1);
    const report = await readReport(output);
    assert.equal(report.gates.releaseRollback.ok, false);
    assert.match(
      report.gates.releaseRollback.errors.join(" "),
      /modelSizeBytes|sha256|differs from current-state replay/,
    );
    await writeFile(fixture.currentModelPath, fixture.currentModelBytes);
  });
});
