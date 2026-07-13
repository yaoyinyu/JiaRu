import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_IMAGE_FILE_BYTES,
  validateImageUpload,
} from "../src/lib/image-upload-validation.ts";

function file(type: string, size = 1024): Blob & { type: string; size: number } {
  return { type, size } as Blob & { type: string; size: number };
}

test("image upload validation accepts supported, decodable dimensions", async () => {
  const result = await validateImageUpload(file("image/jpeg"), async () => ({
    width: 1200,
    height: 1600,
  }));
  assert.deepEqual(result, { ok: true, width: 1200, height: 1600 });
});

test("image upload validation rejects unsupported MIME and oversized files before decoding", async () => {
  let decodeCalls = 0;
  const decode = async () => {
    decodeCalls++;
    return { width: 1000, height: 1000 };
  };

  assert.equal((await validateImageUpload(file("image/gif"), decode)).ok, false);
  assert.equal(
    (await validateImageUpload(file("image/png", MAX_IMAGE_FILE_BYTES + 1), decode)).ok,
    false
  );
  assert.equal(decodeCalls, 0);
});

test("image upload validation reports decode failures and invalid dimensions", async () => {
  const failed = await validateImageUpload(file("image/webp"), async () => {
    throw new Error("corrupt");
  });
  assert.deepEqual(failed.ok ? null : failed.code, "decode_failed");

  const invalid = await validateImageUpload(file("image/png"), async () => ({
    width: 0,
    height: 800,
  }));
  assert.deepEqual(invalid.ok ? null : invalid.code, "decode_failed");
});

test("image upload validation enforces minimum and maximum dimensions", async () => {
  const small = await validateImageUpload(file("image/png"), async () => ({
    width: 319,
    height: 800,
  }));
  assert.deepEqual(small.ok ? null : small.code, "resolution_too_small");

  const large = await validateImageUpload(file("image/png"), async () => ({
    width: 4097,
    height: 800,
  }));
  assert.deepEqual(large.ok ? null : large.code, "resolution_too_large");
});
