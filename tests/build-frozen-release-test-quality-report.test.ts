import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { linkSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-frozen-release-test-quality-report.py");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

function sha(value: unknown): string {
  return createHash("sha256").update(typeof value === "string" ? value : canonical(value)).digest("hex");
}

type Profile = {
  images: number;
  masks: number;
  coreImages: number;
  stressImages: number;
  parentSourceGroups: number;
  schemaVersion?: number;
};

function fixture(profile: Profile) {
  const root = mkdtempSync(path.join(tmpdir(), "frozen-quality-"));
  const write = (name: string, value: unknown) => {
    const file = path.join(root, name);
    writeFileSync(file, JSON.stringify(value));
    return file;
  };
  const baseMasks = Math.floor(profile.masks / profile.images);
  const remainder = profile.masks - baseMasks * profile.images;
  const items = Array.from({ length: profile.images }, (_, index) => ({
    lane: index < profile.coreImages ? "core" : "stress",
    fileName: `${index}.jpg`,
    sourceGroup: `source-${index % profile.parentSourceGroups}`,
    parentSourceGroup: `parent-${index % profile.parentSourceGroups}`,
    imageSha256: sha(`image-${index}`),
    annotationSha256: sha(`annotation-${index}`),
    maskCount: baseMasks + (index < remainder ? 1 : 0),
    trainingUse: "prohibited",
  }));
  const snapshotDocument: Record<string, unknown> = {
    snapshotId: `snapshot-${profile.images}`,
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: {
      images: profile.images,
      masks: profile.masks,
      coreImages: profile.coreImages,
      stressImages: profile.stressImages,
      parentSourceGroups: profile.parentSourceGroups,
    },
    itemsSha256: sha(items),
    items,
    representativeReleaseGate: {
      ok: profile.images >= 100,
      actual: profile.images,
      required: 100,
      shortfall: Math.max(0, 100 - profile.images),
    },
  };
  if (profile.schemaVersion) {
    snapshotDocument.schemaVersion = profile.schemaVersion;
    snapshotDocument.sourceIsolation = {
      ok: true,
      trainValidationOverlap: 0,
      trainReleaseTestOverlap: 0,
      validationReleaseTestOverlap: 0,
      baseSupplementalOverlap: 0,
    };
  }
  const snapshot = write("snapshot.json", snapshotDocument);
  const evaluationRoot = path.join(root, "evaluation");
  let materializationDocument: Record<string, unknown>;
  if (profile.schemaVersion) {
    const records = items.map((item) => ({
      lane: item.lane,
      sourceFileName: item.fileName,
      sourceGroup: item.sourceGroup,
      parentSourceGroup: item.parentSourceGroup,
      maskCount: item.maskCount,
      sourceImageSha256: item.imageSha256,
      sourceAnnotationSha256: item.annotationSha256,
    }));
    const fileRecords = Array.from({ length: profile.images * 2 + 4 }, (_, index) => ({
      path: `artifact-${index}`,
      sha256: sha(`artifact-${index}`),
    }));
    const snapshotSha256 = createHash("sha256").update(readFileSync(snapshot)).digest("hex");
    const invariants = Object.fromEntries([
      "sourceFrozenManifestHashBound", "sourceItemsHashRecomputed", "sourceFilesHashRecomputed",
      "materializedImagesMatchFrozenManifest", "materializedLabelsHashBound", "fixedEvaluationOnlySplit",
      "testSplitNonEmpty", "trainSplitEmpty", "validationSplitEmpty", "coreStressNestedLayout",
      "validPolygons", "pairwiseZeroOverlap", "trainingIdentityIsolationRecomputed",
      "transactionalMaterialization", "targetsNotReused", "noOrphans",
    ].map((name) => [name, true]));
    materializationDocument = {
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision: "evaluation_only_frozen_reviewed_snapshot",
      trainingUse: "prohibited",
      inputs: { sourceFrozenManifest: { path: snapshot, sha256: snapshotSha256, itemsSha256: sha(items) } },
      sourceFrozenManifest: snapshot,
      sourceFrozenManifestSha256: snapshotSha256,
      sourceItemsSha256: sha(items),
      outputDir: evaluationRoot,
      counts: {
        images: profile.images,
        masks: profile.masks,
        coreImages: profile.coreImages,
        stressImages: profile.stressImages,
        trainImages: 0,
        validationImages: 0,
        testImages: profile.images,
        parentSourceGroups: profile.parentSourceGroups,
      },
      sourceIsolation: {
        sourceGroupOverlap: [], parentSourceGroupOverlap: [], exactImageHashOverlap: [], fileNameOverlap: [],
      },
      recordsSha256: sha(records),
      records,
      file_records: fileRecords,
      files_sha256: sha(fileRecords),
      datasetFiles: fileRecords,
      datasetFilesSha256: sha(fileRecords),
      invariants,
      errors: [],
    };
  } else {
    materializationDocument = {
      ok: true,
      trainingUse: "prohibited",
      outputDir: evaluationRoot,
      counts: { images: profile.images, masks: profile.masks, parentSourceGroups: profile.parentSourceGroups },
      sourceIsolation: { parentSourceGroupOverlap: [], exactImageHashOverlap: [] },
    };
  }
  const materialization = write("materialization.json", materializationDocument);
  const artifact = (name: string, count: number) => write(`${name}-artifacts.json`, { split: "test", counts: { prediction_labels: count } });
  const weights = path.join(root, "candidate.pt");
  writeFileSync(weights, "candidate-weights");
  const metric = (name: string, size: number, count: number, box: number, mask: number) => write(`${name}.json`, {
    split: "test",
    imgsz: size,
    dataset_root: evaluationRoot,
    weights,
    box_map50: box,
    seg_map50: mask,
    box_map: box - 0.3,
    seg_map: mask - 0.3,
    evaluation_artifacts: { index: artifact(name, count), counts: { prediction_labels: count } },
  });
  const baselineValues = { boxMap50: 0.86, maskMap50: 0.84, boxMap50To95: 0.6, maskMap50To95: 0.56 };
  const baselineArtifact = artifact("baseline", 13);
  const baseline = write("baseline.json", {
    split: "test",
    imgsz: 512,
    dataset_root: path.join(root, "historical-baseline"),
    weights,
    box_map50: baselineValues.boxMap50,
    seg_map50: baselineValues.maskMap50,
    box_map: baselineValues.boxMap50To95,
    seg_map: baselineValues.maskMap50To95,
    evaluation_artifacts: { index: baselineArtifact, counts: { prediction_labels: 13 } },
  });
  const full512 = metric("full512", 512, profile.images, 0.84, 0.82);
  const full640 = metric("full640", 640, profile.images, 0.88, 0.86);
  const core = metric("core", 512, profile.coreImages, 0.855, 0.83);
  const stress = metric("stress", 512, profile.stressImages, 0.82, 0.78);
  const candidates = [
    { label: `release${profile.images}`, metricsPath: full512, metrics: { boxMap50: 0.84, maskMap50: 0.82, boxMap50To95: 0.54, maskMap50To95: 0.52 }, qualityGatePassed: false },
    { label: `core${profile.coreImages}`, metricsPath: core, metrics: { boxMap50: 0.855, maskMap50: 0.83, boxMap50To95: 0.555, maskMap50To95: 0.53 }, qualityGatePassed: true },
    { label: `stress${profile.stressImages}`, metricsPath: stress, metrics: { boxMap50: 0.82, maskMap50: 0.78, boxMap50To95: 0.52, maskMap50To95: 0.48 }, qualityGatePassed: false },
  ];
  const assessment = write("assessment.json", {
    ok: false,
    baseline: { metricsPath: baseline, metrics: baselineValues },
    thresholds: { maxBoxMap50Drop: 0.02, maxMaskMap50Drop: 0.02, minBoxMap50: 0.85, minMaskMap50: 0.75 },
    candidates,
  });
  const output = path.join(root, "quality.json");
  const args = [
    script,
    "--snapshot-manifest", snapshot,
    "--materialization-report", materialization,
    "--baseline-metrics", baseline,
    "--full-512", full512,
    "--full-640", full640,
    "--core-512", core,
    "--stress-512", stress,
    "--assessment", assessment,
    "--output", output,
  ];
  return {
    root, output, args, snapshot, snapshotDocument, materialization,
    materializationDocument, assessment, candidates, baseline, full512, stress,
  };
}

test("keeps the reviewed 67/384 snapshot compatible and rejects its deployment quality", () => {
  const value = fixture({ images: 67, masks: 384, coreImages: 45, stressImages: 22, parentSourceGroups: 18 });
  execFileSync("python", value.args);
  const report = JSON.parse(readFileSync(value.output, "utf8"));
  assert.equal(report.qualityGatePassed, false);
  assert.equal(report.decision, "reject_candidate_release_at_deployment_resolution");
  assert.deepEqual(report.snapshot.counts, { images: 67, masks: 384, coreImages: 45, stressImages: 22 });
  assert.deepEqual(report.deploymentContract.requiredAssessmentLabels, ["release67", "core45", "stress22"]);
  assert.match(report.errors.join(" "), /release67: box mAP50/);
  assert.match(report.errors.join(" "), /representative release-test scale 67\/100 is incomplete/);
  assert.equal(report.candidateEvidence.sameWeightsAcrossBaselineAndFrozenEvaluations, true);
  assert.equal(report.evaluations.stress512.predictionLabels, 22);
  const verified = JSON.parse(execFileSync("python", [script, "--verify-report", value.output], { encoding: "utf8" }));
  assert.equal(verified.ok, true);
  assert.equal(verified.qualityGatePassed, false);
});

test("binds the 100/554 snapshot schema and never promotes when a 512 subset fails", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  execFileSync("python", value.args);
  const report = JSON.parse(readFileSync(value.output, "utf8"));
  assert.equal(report.qualityGatePassed, false);
  assert.equal(report.snapshot.parentSourceGroups, 29);
  assert.deepEqual(report.snapshot.counts, { images: 100, masks: 554, coreImages: 78, stressImages: 22 });
  assert.deepEqual(report.deploymentContract.requiredAssessmentLabels, ["release100", "core78", "stress22"]);
  assert.equal(report.assessmentPassed.core78, true);
  assert.equal(report.assessmentPassed.stress22, false);
  assert.ok(report.nextActions.some((item: string) => item.includes("100-image representative snapshot")));
});

test("rejects snapshot count drift instead of accepting a renamed population", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  const changed = structuredClone(value.snapshotDocument) as { counts: { masks: number } };
  changed.counts.masks = 553;
  writeFileSync(value.snapshot, JSON.stringify(changed));
  const result = spawnSync("python", value.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /mask or parent-source count drifted/);
});

test("rejects assessment labels that do not describe the current snapshot", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  const assessment = JSON.parse(readFileSync(value.assessment, "utf8"));
  assessment.candidates[1].label = "core45";
  writeFileSync(value.assessment, JSON.stringify(assessment));
  const result = spawnSync("python", value.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /assessment labels/);
});

test("rejects materialization snapshot-hash evidence drift", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  const materialization = structuredClone(value.materializationDocument) as { sourceFrozenManifestSha256: string };
  materialization.sourceFrozenManifestSha256 = "0".repeat(64);
  writeFileSync(value.materialization, JSON.stringify(materialization));
  const result = spawnSync("python", value.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /snapshot binding drifted/);
});

test("refuses direct-input and hard-link output aliases without changing evidence", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  const directArgs = [...value.args];
  directArgs[directArgs.indexOf("--output") + 1] = value.assessment;
  const assessmentBefore = readFileSync(value.assessment);
  const direct = spawnSync("python", directArgs, { encoding: "utf8" });
  assert.notEqual(direct.status, 0);
  assert.match(direct.stderr, /must not overwrite input assessment/);
  assert.deepEqual(readFileSync(value.assessment), assessmentBefore);

  const hardLink = path.join(value.root, "baseline-hardlink.json");
  linkSync(value.args[value.args.indexOf("--baseline-metrics") + 1], hardLink);
  const hardLinkArgs = [...value.args];
  hardLinkArgs[hardLinkArgs.indexOf("--output") + 1] = hardLink;
  const baselineBefore = readFileSync(hardLink);
  const alias = spawnSync("python", hardLinkArgs, { encoding: "utf8" });
  assert.notEqual(alias.status, 0);
  assert.match(alias.stderr, /hard-link alias must not overwrite input baseline_metrics/);
  assert.deepEqual(readFileSync(hardLink), baselineBefore);
});

test("rejects a baseline that is not a verified deployment-512 test evaluation", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  const baseline = JSON.parse(readFileSync(value.baseline, "utf8"));
  baseline.imgsz = 640;
  writeFileSync(value.baseline, JSON.stringify(baseline));
  const result = spawnSync("python", value.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /baseline is not a deployment-512 test evaluation/);
});

test("rejects frozen subset metrics evaluated with different candidate weights", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  const otherWeights = path.join(value.root, "other-candidate.pt");
  writeFileSync(otherWeights, "different-candidate-weights");
  const stress = JSON.parse(readFileSync(value.stress, "utf8"));
  stress.weights = otherWeights;
  writeFileSync(value.stress, JSON.stringify(stress));
  const result = spawnSync("python", value.args, { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /do not use the same candidate weights/);
});

test("deep verification rejects a handwritten outer decision", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  execFileSync("python", value.args);
  const report = JSON.parse(readFileSync(value.output, "utf8"));
  report.qualityGatePassed = true;
  report.decision = "accept_candidate_release";
  writeFileSync(value.output, JSON.stringify(report));
  const result = spawnSync("python", [script, "--verify-report", value.output], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /differs from the deep replay result/);
});

test("deep verification rejects source metric drift after report creation", () => {
  const value = fixture({ images: 100, masks: 554, coreImages: 78, stressImages: 22, parentSourceGroups: 29, schemaVersion: 2 });
  execFileSync("python", value.args);
  const metric = JSON.parse(readFileSync(value.full512, "utf8"));
  metric.box_map50 = 0.83;
  writeFileSync(value.full512, JSON.stringify(metric));
  const result = spawnSync("python", [script, "--verify-report", value.output], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /evidence replay failed/);
});
