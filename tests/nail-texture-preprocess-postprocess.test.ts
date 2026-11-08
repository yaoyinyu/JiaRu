import assert from "node:assert/strict";
import test from "node:test";
import {
  estimateMaskPrincipalAngle,
  postprocessNailTextureDetections,
  preprocessNailTextureImage,
  stabilizeNailTextureCandidateAngles,
} from "../src/lib/nail-texture-recognition/index.ts";

// 2×1 源在双线性映射下恰取整数列（sx=0/1，fx=0，右列触发 sx≥srcW−1 钳边），期望值与最近邻一致。
test("preprocessNailTextureImage creates CHW float tensor", () => {
  const source = {
    width: 2,
    height: 1,
    data: new Uint8ClampedArray([
      255, 0, 0, 255,
      0, 128, 255, 255,
    ]),
  };
  const result = preprocessNailTextureImage(source, 2);
  assert.deepEqual(result.tensorShape, [1, 3, 2, 2]);
  assert.equal(result.tensorData[0], 1);
  assert.equal(result.tensorData[4], 0);
  assert.ok(result.tensorData[8] >= 0 && result.tensorData[8] <= 1);
});

// 4×2 横向图的 sx/sy 全为整数（fx=fy=0），上下各补一行 114/255 padding；期望值与最近邻一致。
test("preprocessNailTextureImage letterboxes landscape input without stretching", () => {
  const source = {
    width: 4,
    height: 2,
    data: new Uint8ClampedArray([
      255, 0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255,
      0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255,
    ]),
  };

  const result = preprocessNailTextureImage(source, 4);

  assert.equal(result.resizeScale, 1);
  assert.equal(result.resizedWidth, 4);
  assert.equal(result.resizedHeight, 2);
  assert.equal(result.padLeft, 0);
  assert.equal(result.padTop, 1);
  assert.ok(Math.abs(result.tensorData[0] - 114 / 255) < 1e-6);
  assert.equal(result.tensorData[4], 1);
  assert.equal(result.tensorData[16 + 8], 1);
});

// 2×2 → 2×2 恒等：sx = fround((x+0.5)·1 − 0.5) = x 为整数列，fx/fy 全为 0，输出与源逐像素相同。
test("preprocessNailTextureImage keeps a 2x2 to 2x2 mapping identical under bilinear resampling", () => {
  const source = {
    width: 2,
    height: 2,
    data: new Uint8ClampedArray([
      10, 20, 30, 255,
      40, 50, 60, 255,
      70, 80, 90, 255,
      110, 120, 130, 255,
    ]),
  };
  const result = preprocessNailTextureImage(source, 2);
  const channelValues = [
    [10, 40, 70, 110], // R：像素顺序 (0,0) (1,0) (0,1) (1,1)
    [20, 50, 80, 120], // G
    [30, 60, 90, 130], // B
  ];
  for (let channel = 0; channel < 3; channel++) {
    for (let index = 0; index < 4; index++) {
      assert.equal(
        result.tensorData[channel * 4 + index],
        Math.fround(channelValues[channel][index] / 255)
      );
    }
  }
});

// 4×4 → 2×2：sx = fround((x+0.5)·2 − 0.5) = 0.5/2.5，fx=fy=0.5 的四邻域均值；
// dst(0,0) 与 dst(1,1) 混到 0/255 棋盘上 → 均值 127.5 → Math.round(127.5) = 128。
test("preprocessNailTextureImage downsamples 4x4 to 2x2 with bilinear averaging", () => {
  const source = { width: 4, height: 4, data: new Uint8ClampedArray(4 * 4 * 4) };
  const red = [
    [0, 255, 0, 0],
    [0, 255, 0, 0],
    [0, 0, 0, 255],
    [0, 0, 0, 255],
  ];
  for (let y = 0; y < 4; y++) {
    for (let x = 0; x < 4; x++) {
      const offset = (y * 4 + x) * 4;
      source.data[offset] = red[y][x];
      source.data[offset + 3] = 255;
    }
  }

  const result = preprocessNailTextureImage(source, 2);

  assert.equal(result.resizedWidth, 2);
  assert.equal(result.resizedHeight, 2);
  assert.equal(result.padLeft, 0);
  assert.equal(result.padTop, 0);
  // R 通道：dst(0,0)=dst(1,1)=128/255，dst(1,0)=dst(0,1)=0；G/B 全 0。
  assert.equal(result.tensorData[0], Math.fround(128 / 255));
  assert.equal(result.tensorData[1], 0);
  assert.equal(result.tensorData[2], 0);
  assert.equal(result.tensorData[3], Math.fround(128 / 255));
  for (let index = 4; index < 12; index++) {
    assert.equal(result.tensorData[index], 0);
  }
});

// 2×2 → 4×4：sx = (x+0.5)·0.5 − 0.5 → x=0 取 −0.25（负向钳边 fx=0）、x=3 取 1.25（≥srcW−1 钳边），
// x=1/2 取 0.25/0.75 真插值。R 通道水平渐变 → 每行 [0,64,191,255]/255（64=round(63.75)、191=round(191.25)），
// G 通道垂直渐变 → 每行 [255,191,64,0]/255，B 全 0。
test("preprocessNailTextureImage upscales 2x2 to 4x4 with bilinear weights and edge clamping", () => {
  const source = {
    width: 2,
    height: 2,
    data: new Uint8ClampedArray([
      0, 255, 0, 255,
      255, 255, 0, 255,
      0, 0, 0, 255,
      255, 0, 0, 255,
    ]),
  };

  const result = preprocessNailTextureImage(source, 4);

  assert.equal(result.resizeScale, 2);
  assert.equal(result.resizedWidth, 4);
  assert.equal(result.resizedHeight, 4);
  const redExpected = [0, 64, 191, 255];
  const greenExpected = [255, 191, 64, 0];
  for (let y = 0; y < 4; y++) {
    for (let x = 0; x < 4; x++) {
      assert.equal(result.tensorData[y * 4 + x], Math.fround(redExpected[x] / 255));
      assert.equal(result.tensorData[16 + y * 4 + x], Math.fround(greenExpected[y] / 255));
      assert.equal(result.tensorData[32 + y * 4 + x], 0);
    }
  }
});

test("postprocessNailTextureDetections reverses letterbox padding", () => {
  const preprocess = preprocessNailTextureImage(
    {
      width: 400,
      height: 200,
      data: new Uint8ClampedArray(400 * 200 * 4),
    },
    640
  );

  const [candidate] = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 1, 6],
        data: new Float32Array([320, 320, 96, 128, 0.95, 0]),
      },
    },
    preprocess
  );

  assert.ok(Math.abs(candidate.cx - 200) < 0.01);
  assert.ok(Math.abs(candidate.cy - 100) < 0.01);
  assert.ok(Math.abs(candidate.width - 60) < 0.01);
  assert.ok(Math.abs(candidate.length - 80) < 0.01);
});

test("postprocessNailTextureDetections transposes channel-major Ultralytics rows", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 6, 2],
        data: new Float32Array([
          120, 360,
          160, 180,
          60, 58,
          100, 96,
          0.95, 0.82,
          0, 0,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 2);
  assert.ok(Math.abs(candidates[0].cx - 120) < 0.01);
  assert.ok(Math.abs(candidates[1].cx - 360) < 0.01);
  assert.equal(candidates[0].confidence, "high");
});

test("postprocessNailTextureDetections maps model rows to candidates", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 860,
    originalHeight: 645,
    scaleX: 860 / 640,
    scaleY: 645 / 640,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 2, 6],
        data: new Float32Array([
          100, 120, 60, 100, 0.9, 0,
          260, 140, 55, 95, 0.6, 0,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 2);
  assert.equal(candidates[0].source, "model");
  assert.equal(candidates[0].suggestedFinger, null);
  assert.ok(candidates[0].cx < candidates[1].cx);
  assert.equal(candidates[0].confidence, "high");
  assert.equal(candidates[1].confidence, "medium");
});

test("postprocessNailTextureDetections respects maxCandidates option", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 860,
    originalHeight: 645,
    scaleX: 860 / 640,
    scaleY: 645 / 640,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 3, 6],
        data: new Float32Array([
          100, 120, 60, 100, 0.95, 0,
          260, 140, 55, 95, 0.85, 0,
          420, 160, 52, 92, 0.75, 0,
        ]),
      },
    },
    preprocess,
    { maxCandidates: 2 }
  );

  assert.equal(candidates.length, 2);
});

test("postprocessNailTextureDetections suppresses duplicate model rows", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 3, 6],
        data: new Float32Array([
          120, 160, 60, 100, 0.94, 0,
          123, 162, 58, 98, 0.82, 0,
          260, 160, 58, 98, 0.78, 0,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 2);
  assert.ok(candidates.some((candidate) => Math.abs(candidate.cx - 120) < 0.01));
  assert.ok(candidates.some((candidate) => Math.abs(candidate.cx - 260) < 0.01));
});

test("postprocessNailTextureDetections can expose low-score rows for debug mode", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const outputs = {
    output0: {
      dims: [1, 1, 6],
      data: new Float32Array([120, 160, 60, 100, 0.28, 0]),
    },
  };

  assert.equal(postprocessNailTextureDetections(outputs, preprocess).length, 0);

  const debugCandidates = postprocessNailTextureDetections(outputs, preprocess, {
    includeLowConfidenceCandidates: true,
  });

  assert.equal(debugCandidates.length, 1);
  assert.equal(debugCandidates[0].confidence, "low");
  assert.ok(debugCandidates[0].warnings?.includes("low_score_debug_candidate"));
});

test("postprocessNailTextureDetections defaults to keeping up to 10 candidates", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const rows: number[] = [];
  for (let index = 0; index < 12; index++) {
    rows.push(40 + index * 20, 120 + index * 5, 48, 88, 0.95 - index * 0.01, 0);
  }

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 12, 6],
        data: new Float32Array(rows),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 10);
});

test("postprocessNailTextureDetections keeps finger suggestions null for 1 to 3 candidates", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 3, 6],
        data: new Float32Array([
          120, 120, 60, 100, 0.95, 0,
          260, 140, 55, 95, 0.85, 0,
          420, 160, 52, 92, 0.75, 0,
        ]),
      },
    },
    preprocess
  );

  assert.deepEqual(candidates.map((candidate) => candidate.suggestedFinger), [null, null, null]);
});

test("postprocessNailTextureDetections maps 4 candidates to index through pinky", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 4, 6],
        data: new Float32Array([
          80, 120, 60, 100, 0.98, 0,
          180, 130, 58, 96, 0.91, 0,
          280, 140, 55, 92, 0.84, 0,
          380, 150, 52, 88, 0.77, 0,
        ]),
      },
    },
    preprocess
  );

  assert.deepEqual(candidates.map((candidate) => candidate.suggestedFinger), [1, 2, 3, 4]);
});

test("estimateMaskPrincipalAngle and postprocess keep a stable mask-derived angle", () => {
  const angle = estimateMaskPrincipalAngle({
    width: 5,
    height: 5,
    data: new Uint8Array([
      0, 0, 0, 0, 0,
      0, 1, 1, 1, 0,
      0, 1, 1, 1, 0,
      0, 0, 0, 0, 0,
      0, 0, 0, 0, 0,
    ]),
    originX: 0,
    originY: 0,
    scale: 1,
  });

  assert.ok(typeof angle === "number");
  assert.ok(Math.abs(Math.abs(angle ?? 0) - Math.PI / 2) < 0.15);

  const preprocess = {
    inputSize: 640,
    originalWidth: 640,
    originalHeight: 640,
    scaleX: 1,
    scaleY: 1,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 1, 6],
        data: new Float32Array([320, 320, 260, 60, 0.95, 1]),
      },
      output1: {
        dims: [1, 1, 8, 8],
        data: new Float32Array([
          -8, -8, -8, -8, -8, -8, -8, -8,
          -8, -8, -8, -8, -8, -8, -8, -8,
          -8, -8, -8, -8, -8, -8, -8, -8,
          -8, -8, 8, 8, 8, 8, -8, -8,
          -8, -8, -8, -8, -8, -8, -8, -8,
          -8, -8, -8, -8, -8, -8, -8, -8,
          -8, -8, -8, -8, -8, -8, -8, -8,
          -8, -8, -8, -8, -8, -8, -8, -8,
        ]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 1);
  assert.ok(Math.abs(Math.abs(candidates[0].angle) - Math.PI / 2) < 0.2);
});

test("stabilizeNailTextureCandidateAngles borrows group angle for ambiguous candidates", () => {
  const stabilized = stabilizeNailTextureCandidateAngles(
    [
      {
        id: "model-1",
        cx: 120,
        cy: 200,
        width: 48,
        length: 120,
        angle: Math.PI / 2,
        score: 0.88,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
      {
        id: "model-2",
        cx: 260,
        cy: 210,
        width: 80,
        length: 84,
        angle: 0,
        score: 0.82,
        confidence: "high",
        source: "model",
        suggestedFinger: null,
      },
    ],
    [{ reliable: true }, { reliable: false }]
  );

  assert.ok(Math.abs(Math.abs(stabilized[1].angle) - Math.PI / 2) < 0.01);
  assert.ok(stabilized[1].warnings?.includes("angle_stabilized_from_group"));
});

test("postprocessNailTextureDetections defaults ambiguous no-mask candidates to vertical angle", () => {
  const preprocess = {
    inputSize: 640,
    originalWidth: 860,
    originalHeight: 645,
    scaleX: 860 / 640,
    scaleY: 645 / 640,
    tensorData: new Float32Array(),
    tensorShape: [1, 3, 640, 640] as [1, 3, number, number],
  };

  const candidates = postprocessNailTextureDetections(
    {
      output0: {
        dims: [1, 1, 6],
        data: new Float32Array([320, 320, 78, 80, 0.91, 0]),
      },
    },
    preprocess
  );

  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].angle, 0);
  assert.ok(candidates[0].warnings?.includes("angle_defaulted_vertical"));
});
