import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("browser entry keeps Node filesystem/crypto debug tools in their separate module", async () => {
  const source = await readFile(new URL("../src/lib/nail-texture-recognition/index.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /from\s+["'][^"']*debug-artifacts/);
});

test("recognition worker avoids the client entry that constructs another worker", async () => {
  const source = await readFile(new URL("../src/workers/nail-texture-recognition.worker.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /from\s+["']@\/lib\/nail-texture-recognition["']/);
  assert.match(source, /from\s+["']@\/lib\/nail-texture-recognition\/recognize["']/);
});
