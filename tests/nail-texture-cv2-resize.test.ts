// cv2.resize INTER_LINEAR 8U（C3）逐位复刻的对拍测试。
//
// fixture 由 model/training/oneoff/generate-cv2-resize-fixtures-v1.py 用本机 cv2
// （INTER_LINEAR，随机固定 seed 图 + 同尺度小图覆盖生产 letterbox 的 1.5625 尺度）
// 生成；期望输出为 cv2 实算字节。断言：逐字节完全相等。
// 生产真实图（600x800→384x512）的逐位验证在 parity 链
// （model/reviews/geometry64-browser-parity-v1/letterbox-check.json）中复核。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import test from "node:test";
import { resizeLinearC3Cv2BitExact } from "../src/lib/nail-texture-recognition/preprocess.ts";

const fixturePath = fileURLToPath(new URL("./fixtures/cv2-resize-fixture.json", import.meta.url));
const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as Cv2ResizeFixture;

interface Cv2ResizeFixture {
  cv2Version: string;
  cases: {
    id: number;
    label: string;
    src: [number, number];
    dst: [number, number];
    inputBase64: string;
    expectedBase64: string;
  }[];
}

for (const testCase of fixture.cases) {
  test(`cv2 resize bit-exact case ${testCase.id} ${testCase.src}->${testCase.dst} (${testCase.label})`, () => {
    const input = new Uint8Array(Buffer.from(testCase.inputBase64, "base64"));
    const expected = new Uint8Array(Buffer.from(testCase.expectedBase64, "base64"));
    const got = resizeLinearC3Cv2BitExact(
      input,
      testCase.src[0],
      testCase.src[1],
      testCase.dst[0],
      testCase.dst[1]
    );
    assert.equal(got.length, expected.length);
    let diffCount = 0;
    let maxAbs = 0;
    for (let index = 0; index < expected.length; index++) {
      if (got[index] !== expected[index]) {
        diffCount++;
        maxAbs = Math.max(maxAbs, Math.abs(got[index] - expected[index]));
      }
    }
    assert.equal(
      diffCount,
      0,
      `case ${testCase.id}: ${diffCount} bytes differ, maxAbs ${maxAbs}`
    );
  });
}
