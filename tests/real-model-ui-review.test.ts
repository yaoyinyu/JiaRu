import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { validateRealModelUiReviewRecord } from "../src/lib/nail-texture-recognition/first-run-record.ts";

test("real model ui review template is structurally valid", async () => {
  const record = JSON.parse(
    await readFile(
      path.resolve("model/fixtures/real-model-ui-review.template.json"),
      "utf8"
    )
  );

  const validation = validateRealModelUiReviewRecord(record);
  assert.equal(validation.ok, true);
  assert.deepEqual(validation.errors, []);
});
