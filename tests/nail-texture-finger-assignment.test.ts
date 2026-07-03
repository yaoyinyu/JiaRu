import assert from "node:assert/strict";
import test from "node:test";
import { inferSuggestedFingers } from "../src/lib/nail-texture-recognition/index.ts";

test("inferSuggestedFingers leaves 1 to 3 candidates unassigned", () => {
  assert.deepEqual(inferSuggestedFingers(1), [null]);
  assert.deepEqual(inferSuggestedFingers(2), [null, null]);
  assert.deepEqual(inferSuggestedFingers(3), [null, null, null]);
});

test("inferSuggestedFingers maps 4 candidates to index through pinky", () => {
  assert.deepEqual(inferSuggestedFingers(4), [1, 2, 3, 4]);
});

test("inferSuggestedFingers maps 5 candidates to thumb through pinky and leaves extras unknown", () => {
  assert.deepEqual(inferSuggestedFingers(5), [0, 1, 2, 3, 4]);
  assert.deepEqual(inferSuggestedFingers(7), [0, 1, 2, 3, 4, null, null]);
});
