import assert from "node:assert/strict";
import test from "node:test";
import {
  assessNailTextureCandidate,
  rankNailTextureCandidates,
} from "../src/lib/nail-texture-recognition/index.ts";

test("rankNailTextureCandidates filters implausible areas and keeps best candidates", () => {
  const ranked = rankNailTextureCandidates(
    [
      {
        id: "good",
        cx: 100,
        cy: 120,
        length: 90,
        width: 45,
        angle: 0,
        score: 0.9,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
      {
        id: "too-big",
        cx: 200,
        cy: 120,
        length: 400,
        width: 300,
        angle: 0,
        score: 0.8,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
      {
        id: "too-small",
        cx: 300,
        cy: 120,
        length: 6,
        width: 3,
        angle: 0,
        score: 0.7,
        confidence: "medium",
        source: "model",
        suggestedFinger: null,
      },
    ],
    {
      imageWidth: 860,
      imageHeight: 645,
    }
  );

  assert.equal(ranked.length, 1);
  assert.equal(ranked[0].id, "good");
});

test("rankNailTextureCandidates defaults to keeping up to 10 candidates", () => {
  const candidates = Array.from({ length: 12 }, (_, index) => ({
    id: `candidate-${index + 1}`,
    cx: 40 + index * 20,
    cy: 120,
    length: 90,
    width: 45,
    angle: 0,
    score: 0.95 - index * 0.01,
    confidence: "high" as const,
    source: "model" as const,
    suggestedFinger: null,
  }));

  const ranked = rankNailTextureCandidates(candidates, {
    imageWidth: 860,
    imageHeight: 645,
  });

  assert.equal(ranked.length, 10);
});

test("rankNailTextureCandidates suppresses highly overlapping duplicate candidates", () => {
  const ranked = rankNailTextureCandidates(
    [
      {
        id: "best-overlap",
        cx: 100,
        cy: 120,
        length: 90,
        width: 45,
        angle: 0,
        score: 0.92,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
      {
        id: "duplicate-overlap",
        cx: 103,
        cy: 122,
        length: 88,
        width: 44,
        angle: 0,
        score: 0.88,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
      {
        id: "separate-nail",
        cx: 210,
        cy: 122,
        length: 86,
        width: 43,
        angle: 0,
        score: 0.8,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
    ],
    {
      imageWidth: 860,
      imageHeight: 645,
    }
  );

  assert.deepEqual(ranked.map((candidate) => candidate.id), [
    "best-overlap",
    "separate-nail",
  ]);
});

test("rankNailTextureCandidates can keep low-score candidates for debug review", () => {
  const candidates = [
    {
      id: "low-score",
      cx: 100,
      cy: 120,
      length: 90,
      width: 45,
      angle: 0,
      score: 0.28,
      confidence: "low" as const,
      source: "model" as const,
      suggestedFinger: null,
    },
  ];

  const defaultRanked = rankNailTextureCandidates(candidates, {
    imageWidth: 860,
    imageHeight: 645,
  });
  assert.equal(defaultRanked.length, 0);

  const debugRanked = rankNailTextureCandidates(candidates, {
    imageWidth: 860,
    imageHeight: 645,
    includeLowConfidenceCandidates: true,
  });

  assert.equal(debugRanked.length, 1);
  assert.equal(debugRanked[0].id, "low-score");
  assert.equal(debugRanked[0].confidence, "low");
  assert.ok(debugRanked[0].warnings?.includes("low_score_debug_candidate"));
});

test("assessNailTextureCandidate surfaces sparse-mask and highlight warnings", () => {
  const sourceImage = {
    width: 100,
    height: 100,
    data: new Uint8ClampedArray(100 * 100 * 4),
  };

  for (let y = 36; y <= 64; y++) {
    for (let x = 36; x <= 64; x++) {
      const offset = (y * sourceImage.width + x) * 4;
      sourceImage.data[offset] = 255;
      sourceImage.data[offset + 1] = 255;
      sourceImage.data[offset + 2] = 255;
      sourceImage.data[offset + 3] = 255;
    }
  }

  const assessment = assessNailTextureCandidate(
    {
      id: "highlighted",
      cx: 50,
      cy: 50,
      length: 30,
      width: 20,
      angle: 0,
      score: 0.92,
      confidence: "high",
      source: "model",
      suggestedFinger: null,
      mask: {
        width: 4,
        height: 4,
        data: new Uint8Array([
          1, 0, 0, 0,
          0, 1, 0, 0,
          0, 0, 1, 0,
          0, 0, 0, 0,
        ]),
        originX: 0,
        originY: 0,
        scale: 1,
      },
    },
    {
      imageWidth: 100,
      imageHeight: 100,
      sourceImage,
    }
  );

  assert.ok(assessment.warnings.includes("dirty_mask_crop"));
  assert.ok(assessment.warnings.includes("mask_crop_touches_edge"));
  assert.ok(assessment.warnings.includes("mask_foreground_too_small"));
  assert.ok(assessment.warnings.includes("highlight_hotspots"));
  assert.ok(assessment.adjustedScore < 0.92);
});
