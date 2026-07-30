import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("example environment does not enable the smoke nail model by default", async () => {
  const source = await readFile(".env.local.example", "utf8");
  const activeAssignments = source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .filter((line) => line.startsWith("NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL="));

  assert.deepEqual(activeAssignments, []);
  assert.match(source, /NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=.*smoke/);
});

test("example environment configures Agnes without committing a real key", async () => {
  const source = await readFile(".env.local.example", "utf8");

  assert.match(source, /^AGNES_API_KEY=your-key-here$/m);
  assert.match(
    source,
    /^AGNES_API_BASE_URL=https:\/\/apihub\.agnes-ai\.com\/v1$/m
  );
  assert.match(source, /^AGNES_IMAGE_MODEL=agnes-image-2\.1-flash$/m);
  assert.doesNotMatch(source, /AGNES_API_KEY=sk-/);
  assert.doesNotMatch(source, /^OPENAI_API_KEY=/m);
});
