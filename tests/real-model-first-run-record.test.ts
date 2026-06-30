import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { validateRealModelFirstRunRecord } from "../src/lib/nail-texture-recognition/first-run-record.ts";

test("real model first run record template is structurally valid", async () => {
  const record = JSON.parse(
    await readFile(
      path.resolve("model/fixtures/real-model-first-run-record.template.json"),
      "utf8"
    )
  );

  const validation = validateRealModelFirstRunRecord(record);
  assert.equal(validation.ok, true);
  assert.deepEqual(validation.errors, []);
});
