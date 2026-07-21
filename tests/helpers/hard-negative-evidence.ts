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

const finalizer = path.resolve(
  "model/training/finalize-reviewed-hard-negative-manifest.py",
);
const python = process.env.PYTHON ?? "python";

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

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

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
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
