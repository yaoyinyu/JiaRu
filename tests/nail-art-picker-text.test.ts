import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const pickerPath = path.resolve("src/components/NailArtPicker.tsx");
const replacementCharacter = String.fromCodePoint(0xfffd);

test("NailArtPicker keeps user-facing progress labels UTF-8 clean", async () => {
  const source = await readFile(pickerPath, "utf8");

  assert.doesNotMatch(source, /鈥/, "picker should not contain visible mojibake fragments");
  assert.ok(
    !source.includes(replacementCharacter),
    "picker should not contain Unicode replacement characters"
  );
  assert.match(source, /Detecting nail regions…/);
  assert.match(source, /Extracting…/);
  assert.match(source, /` · \$\{FINGER_FULL\[region\.assignedFinger\]\}`/);
  assert.doesNotMatch(source, /` 路 \$\{FINGER_FULL\[region\.assignedFinger\]\}`/);
});