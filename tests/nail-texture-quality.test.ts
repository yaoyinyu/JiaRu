import assert from "node:assert/strict";
import test from "node:test";
import { rankNailTextureCandidates } from "../src/lib/nail-texture-recognition/index.ts";

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
