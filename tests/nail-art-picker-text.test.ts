import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const pickerPath = path.resolve("src/components/NailArtPicker.tsx");
const arPagePath = path.resolve("src/app/ar-tryon/page.tsx");
const replacementCharacter = String.fromCodePoint(0xfffd);

test("NailArtPicker keeps user-facing labels UTF-8 clean and fully Chinese", async () => {
  const source = await readFile(pickerPath, "utf8");

  assert.doesNotMatch(source, /鈥/, "picker should not contain visible mojibake fragments");
  assert.ok(
    !source.includes(replacementCharacter),
    "picker should not contain Unicode replacement characters"
  );
  assert.match(source, /正在识别美甲甲面…/);
  assert.match(source, /正在提取…/);
  assert.match(source, /` · \$\{FINGER_NAMES\[region\.assignedFinger\]\}`/);
  assert.match(source, /在图片上添加甲面/);
  assert.match(source, /提取所选纹理/);
  assert.match(source, /手部自动定位/);
  assert.match(source, /优先自动定位五个甲面/);

  for (const englishLabel of [
    "Nail texture picker",
    "Detected regions",
    "Adjust selected region",
    "Assign finger",
    "Quality review",
    "Confirm textures",
    "Add region",
    "Export debug JSON",
    ">Regions:",
    ">Assigned:",
    ">Elapsed:",
  ]) {
    assert.ok(!source.includes(englishLabel), `picker should not expose ${englishLabel}`);
  }
});

test("AR try-on exposes Chinese nail fit controls", async () => {
  const source = await readFile(arPagePath, "utf8");
  assert.match(source, /逐指校准/);
  assert.match(source, /甲面长度/);
  assert.match(source, /甲面宽度/);
  assert.match(source, /aria-label="甲面位置"/);
  assert.match(source, /重置本指/);
  assert.match(source, /重置全部/);
});
