import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { deflateSync } from "node:zlib";

type HardNegativeSource = {
  fileName: string;
  sourceGroup: string;
  imageSha256: string;
  imagePath: string;
};

export type ProtectedRoleEvidence = {
  train: string;
  val: string;
  frozenTest: string;
};

const finalizer = path.resolve(
  "model/training/finalize-reviewed-hard-negative-manifest.py",
);
const python = process.env.PYTHON ?? "python";

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

const canonicalSha = (value: unknown) =>
  createHash("sha256").update(canonicalJson(value)).digest("hex");

let crcTable: Uint32Array | undefined;
const pngBaseCache = new Map<string, { head: Buffer; tail: Buffer }>();

function crc32(data: Buffer) {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let index = 0; index < 256; index++) {
      let value = index;
      for (let bit = 0; bit < 8; bit++) {
        value = (value & 1) !== 0 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      }
      crcTable[index] = value >>> 0;
    }
  }
  let value = 0xffffffff;
  for (const byte of data) value = crcTable[(value ^ byte) & 0xff] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, payload: Buffer) {
  const name = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(payload.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([name, payload])));
  return Buffer.concat([length, name, payload, checksum]);
}

export function writeTestPng(
  file: string,
  seed: number,
  width = 320,
  height = 320,
) {
  mkdirSync(path.dirname(file), { recursive: true });
  const cacheKey = `${width}x${height}`;
  let base = pngBaseCache.get(cacheKey);
  if (!base) {
    const raw = Buffer.alloc((width * 4 + 1) * height);
    for (let y = 0; y < height; y++) {
      const row = y * (width * 4 + 1);
      raw[row] = 0;
      for (let x = 0; x < width; x++) {
        const offset = row + 1 + x * 4;
        raw[offset] = 80;
        raw[offset + 1] = 120;
        raw[offset + 2] = 160;
        raw[offset + 3] = 0xff;
      }
    }
    const header = Buffer.alloc(13);
    header.writeUInt32BE(width, 0);
    header.writeUInt32BE(height, 4);
    header[8] = 8;
    header[9] = 6;
    base = {
      head: Buffer.concat([
        Buffer.from("89504e470d0a1a0a", "hex"),
        pngChunk("IHDR", header),
        pngChunk("IDAT", deflateSync(raw)),
      ]),
      tail: pngChunk("IEND", Buffer.alloc(0)),
    };
    pngBaseCache.set(cacheKey, base);
  }
  const png = Buffer.concat([
    base.head,
    pngChunk("tEXt", Buffer.from(`fixture-seed\0${seed}`, "latin1")),
    base.tail,
  ]);
  writeFileSync(file, png);
}

export function writePatternTestPng(
  file: string,
  seed: number,
  width = 320,
  height = 320,
) {
  mkdirSync(path.dirname(file), { recursive: true });
  const raw = Buffer.alloc((width * 4 + 1) * height);
  const mix = (x: number, y: number) => {
    let value =
      (Math.imul(seed + 1, 0x9e3779b1) ^
        Math.imul(x + 17, 0x85ebca6b) ^
        Math.imul(y + 31, 0xc2b2ae35)) >>>
      0;
    value ^= value >>> 16;
    value = Math.imul(value, 0x7feb352d) >>> 0;
    value ^= value >>> 15;
    value = Math.imul(value, 0x846ca68b) >>> 0;
    return (value ^ (value >>> 16)) >>> 0;
  };
  for (let y = 0; y < height; y++) {
    const row = y * (width * 4 + 1);
    raw[row] = 0;
    for (let x = 0; x < width; x++) {
      const offset = row + 1 + x * 4;
      const value = mix(Math.floor((x * 17) / width), Math.floor((y * 16) / height));
      raw[offset] = value & 0xff;
      raw[offset + 1] = (value >>> 8) & 0xff;
      raw[offset + 2] = (value >>> 16) & 0xff;
      raw[offset + 3] = 0xff;
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 6;
  writeFileSync(
    file,
    Buffer.concat([
      Buffer.from("89504e470d0a1a0a", "hex"),
      pngChunk("IHDR", header),
      pngChunk("IDAT", deflateSync(raw)),
      pngChunk("IEND", Buffer.alloc(0)),
    ]),
  );
}

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

export function createProtectedRoleEvidence(
  root: string,
): ProtectedRoleEvidence {
  const protectedRoot = path.join(root, "protected-role-evidence");
  mkdirSync(protectedRoot, { recursive: true });

  const makeTruthIndex = (
    role: "train" | "val",
    count: number,
    decision: string,
  ) => {
    const truths = Array.from({ length: count }, (_, index) => {
      const report = path.join(
        protectedRoot,
        `${role}-truth-${String(index + 1).padStart(3, "0")}.json`,
      );
      writeJson(report, {
        ok: true,
        decision: `approved-${role}-truth-fixture`,
        sequence: index + 1,
      });
      return {
        reportPath: report,
        reportName: path.basename(report),
        reportSha256: shaFile(report),
        sequence: index + 1,
        fileName: `${role}-protected-${String(index + 1).padStart(3, "0")}.jpg`,
        imageSha256: createHash("sha256")
          .update(`${role}-protected-image-${index + 1}`)
          .digest("hex"),
        sourceGroup: `${role}-protected-group-${index + 1}`,
        completeMaskCount: 1,
      };
    });
    const indexPath = path.join(protectedRoot, `${role}-truth-index.json`);
    writeJson(indexPath, {
      schemaVersion: 1,
      ok: true,
      decision,
      summary: {
        approvedReportCount: count,
        rejectedReportCount: 0,
        uniqueImageCount: count,
        completeMaskCount: count,
        redundantReportCount: 0,
        redundantImageCount: 0,
        conflictingImageCount: 0,
      },
      canonicalTruths: truths,
      errors: [],
      conflicts: [],
    });
    return indexPath;
  };

  const train = makeTruthIndex(
    "train",
    100,
    "approved_unique_training_truth_index",
  );
  const val = makeTruthIndex(
    "val",
    30,
    "approved_unique_validation_truth_index",
  );
  const baseSnapshot = path.join(protectedRoot, "base-snapshot.json");
  const supplementalTruth = path.join(
    protectedRoot,
    "supplemental-truth-index.json",
  );
  writeJson(baseSnapshot, { ok: true, fixture: "base-release-test" });
  writeJson(supplementalTruth, {
    ok: true,
    fixture: "supplemental-release-test",
  });
  const items = Array.from({ length: 100 }, (_, index) => ({
    lane: index < 78 ? "core" : "stress",
    fileName: `frozen-protected-${String(index + 1).padStart(3, "0")}.jpg`,
    parentFileName: `frozen-parent-${String(index + 1).padStart(3, "0")}.jpg`,
    sourceGroup: `frozen-protected-group-${index + 1}`,
    parentSourceGroup: `frozen-parent-group-${index + 1}`,
    imageSha256: createHash("sha256")
      .update(`frozen-image-${index + 1}`)
      .digest("hex"),
    annotationSha256: createHash("sha256")
      .update(`frozen-annotation-${index + 1}`)
      .digest("hex"),
    maskCount: 1,
    authorizedUses: ["independent-release-test", "long-term-regression"],
    trainingUse: "prohibited",
  }));
  const frozenTest = path.join(protectedRoot, "frozen-test-manifest.json");
  writeJson(frozenTest, {
    schemaVersion: 2,
    snapshotId: "protected-fixture-v2",
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    evaluationUse: "permitted",
    inputs: {
      baseSnapshot,
      baseSnapshotSha256: shaFile(baseSnapshot),
      supplementalTruthIndex: supplementalTruth,
      supplementalTruthIndexSha256: shaFile(supplementalTruth),
      trainTruthIndex: train,
      trainTruthIndexSha256: shaFile(train),
      validationTruthIndex: val,
      validationTruthIndexSha256: shaFile(val),
    },
    counts: {
      images: 100,
      masks: 100,
      coreImages: 78,
      stressImages: 22,
    },
    representativeReleaseGate: {
      ok: true,
      actual: 100,
      required: 100,
      shortfall: 0,
    },
    sourceIsolation: {
      ok: true,
      trainValidationOverlap: 0,
      trainReleaseTestOverlap: 0,
      validationReleaseTestOverlap: 0,
      baseSupplementalOverlap: 0,
    },
    itemsSha256: canonicalSha(items),
    items,
  });
  return { train, val, frozenTest };
}

export function createApprovedHardNegativeEvidence(
  root: string,
  sources: HardNegativeSource[],
) {
  const evidenceRoot = path.join(root, "hard-negative-evidence");
  mkdirSync(evidenceRoot, { recursive: true });
  const screening = path.join(evidenceRoot, "source-screening.json");
  const authorization = path.join(evidenceRoot, "authorization.json");
  writeJson(screening, { ok: true, decision: "source-screening-pass" });
  writeJson(authorization, {
    ok: true,
    decision: "A",
    authorizedUses: ["commercial-model-training"],
  });

  const reviewedCandidates = sources.map((source) => ({
    fileName: source.fileName,
    sourcePath: source.imagePath,
    sha256: source.imageSha256,
    width: 320,
    height: 320,
    sourceGroup: source.sourceGroup,
    originalResolutionVisualReview: {
      reviewed: true,
      clearEnoughForHardNegative: true,
      validHumanManicureSurfaceAnywhere: false,
      croppedTargetNail: false,
      collage: false,
      templateOrIndependentNailTip: false,
      reviewNote: "Clear original-resolution negative fixture without a nail surface.",
    },
    authorizationEvidence: {
      decision: "A",
      authorizationEntryFileNameMatch: true,
      authorizationEntrySha256Match: true,
      trainingEligibility: "permitted-after-visual-review-and-source-isolation",
    },
    sourceIsolationEvidence: {
      trainImageShaMatches: 0,
      validationImageShaMatches: 0,
      frozenTestImageShaMatches: 0,
      isolated: true,
    },
    role: "hard-negative-candidate",
    trainingUse: "prohibited",
    materializationStatus: "not-materialized",
    candidateStatus: "pass-candidate-only",
  }));
  const review = path.join(evidenceRoot, "review-decisions.json");
  writeJson(review, {
    ok: true,
    decision: "hard_negative_candidate_scan_complete_candidate_only",
    inputs: {
      sourceScreeningBatch: { path: screening, sha256: shaFile(screening) },
      authorization: {
        path: authorization,
        sha256: shaFile(authorization),
        decision: "A",
        status: "confirmed",
        authorizedUses: [
          "commercial-model-training",
          "independent-release-test",
          "long-term-regression",
        ],
      },
    },
    policy: {
      candidateMustBeClear: true,
      candidateMustContainNoValidHumanManicureSurfaceAnywhere: true,
      candidateMustBeUsefulForDeploymentFalsePositiveSuppression: true,
      candidateMustHaveAuthorizationA: true,
      candidateMustBeSourceIsolatedFromTrainValAndFrozenTest: true,
      rejectTemplates: true,
      rejectIndependentNailTips: true,
      rejectCollages: true,
      rejectLowQuality: true,
      rejectCroppedSources: true,
      candidateOnly: true,
      trainingUse: "prohibited-until-separate-materialization-and-training-authorization",
    },
    candidates: reviewedCandidates,
  });

  const candidateManifest = path.join(evidenceRoot, "candidate-manifest.json");
  writeJson(candidateManifest, {
    ok: true,
    decision: "hard_negative_candidate_manifest_ready_not_materialized",
    candidateOnly: true,
    inputs: {
      reviewDecisionsPath: review,
      reviewDecisionsSha256: shaFile(review),
      sourceScreeningBatchPath: screening,
      sourceScreeningBatchSha256: shaFile(screening),
      authorizationPath: authorization,
      authorizationSha256: shaFile(authorization),
    },
    summary: {
      reviewedImages: sources.length,
      candidateImages: sources.length,
      safeHardNegativeCount: sources.length,
      excludedImages: 0,
    },
    candidates: sources.map((source) => ({
      fileName: source.fileName,
      sourcePath: source.imagePath,
      sha256: source.imageSha256,
      sourceGroup: source.sourceGroup,
      authorization: "A",
      sourceIsolation: "verified-zero-match-train-val-frozen-test",
      humanManicureSurfaceAnywhere: false,
      candidatePurpose: "deployment-false-positive-suppression",
      role: "hard-negative-candidate",
      trainingUse: "prohibited",
      materializationStatus: "not-materialized",
    })),
    gates: {
      allThirtySevenOriginalResolutionReviewed: true,
      allSourceImageHashesMatchBoundScreeningEvidence: true,
      allRelevantShardReportAndDecisionHashesMatch: true,
      authorizationAConfirmed: true,
      candidateSourceIsolatedFromTrain: true,
      candidateSourceIsolatedFromVal: true,
      candidateSourceIsolatedFromFrozenTest: true,
      officialDatasetUnchanged: true,
      sharedSplitUnchanged: true,
      trainingStillProhibited: true,
    },
  });
  const approvedManifest = path.join(evidenceRoot, "approved-manifest.json");
  const result = spawnSync(
    python,
    [
      finalizer,
      "--candidate-manifest",
      candidateManifest,
      "--output",
      approvedManifest,
    ],
    { encoding: "utf8" },
  );
  const expectedStatus = sources.length >= 100 ? 0 : 2;
  if (result.status !== expectedStatus) {
    throw new Error(`hard-negative fixture finalization failed: ${result.stderr}`);
  }
  return {
    approvedManifest,
    approvedDocument: JSON.parse(readFileSync(approvedManifest, "utf8")),
    candidateManifest,
    review,
    screening,
    authorization,
  };
}
