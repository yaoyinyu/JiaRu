import assert from "node:assert/strict";
import test from "node:test";

import {
  presentRecognitionWarning,
  regionNeedsReview,
  summarizeExtractionDiagnostics,
  summarizeRegionQuality,
} from "../src/components/nail-art-picker-quality.ts";

test("presentRecognitionWarning maps known runtime warnings to readable text", () => {
  assert.equal(
    presentRecognitionWarning("worker_unavailable_used_main_thread"),
    "当前环境未启用 Worker，已回退到主线程识别。"
  );
  assert.equal(
    presentRecognitionWarning("unknown_warning_code"),
    "识别提示：unknown_warning_code"
  );
});

test("regionNeedsReview becomes true for low confidence warnings or extraction quality failures", () => {
  assert.equal(regionNeedsReview({ confidence: "high" }), false);
  assert.equal(regionNeedsReview({ confidence: "low" }), true);
  assert.equal(regionNeedsReview({ confidence: "high", warnings: ["highlight_hotspots"] }), true);
  assert.equal(
    regionNeedsReview({
      confidence: "high",
      extractionDiagnostics: {
        quality: {
          ok: false,
          warnings: ["mask_crop_touches_edge"],
        },
        highlightRepair: {
          highlightPixels: 0,
          repairedPixels: 0,
          highlightRatio: 0,
        },
      },
    }),
    true
  );
});

test("summarizeRegionQuality dedupes user-facing review messages", () => {
  const summary = summarizeRegionQuality({
    confidence: "low",
    warnings: ["highlight_hotspots", "mask_crop_touches_edge"],
    extractionDiagnostics: {
      quality: {
        ok: false,
        warnings: ["mask_crop_touches_edge"],
      },
      highlightRepair: {
        highlightPixels: 3,
        repairedPixels: 2,
        highlightRatio: 0.12,
      },
    },
  });

  assert.equal(summary.severity, "review");
  assert.equal(summary.title, "建议复核当前候选");
  assert.ok(summary.messages.includes("当前候选置信度偏低，建议检查位置、角度和大小。"));
  assert.ok(summary.messages.includes("甲面高光较强，可能影响纹理细节。"));
  assert.ok(summary.messages.includes("裁剪区域贴边，可能缺失部分甲面。"));
  assert.equal(
    summary.messages.filter((message) => message === "裁剪区域贴边，可能缺失部分甲面。").length,
    1
  );
});

test("summarizeExtractionDiagnostics builds readable extraction summary", () => {
  const summary = summarizeExtractionDiagnostics({
    quality: {
      ok: false,
      warnings: ["mask_crop_touches_edge", "dirty_mask_crop"],
    },
    highlightRepair: {
      highlightPixels: 5,
      repairedPixels: 3,
      highlightRatio: 0.16,
    },
  });

  assert.ok(summary);
  assert.equal(summary?.severity, "review");
  assert.equal(summary?.title, "当前纹理提取结果建议复核");
  assert.deepEqual(summary?.stats, ["质量：需复核", "高光像素：5", "已修复：3"]);
  assert.ok(summary?.messages.includes("裁剪区域贴边，可能缺失部分甲面。"));
  assert.ok(summary?.messages.includes("裁剪区域混入了较多非甲面像素，建议检查边界。"));
  assert.ok(summary?.messages.includes("检测到高光区域，已对可修复部分做轻微修复。"));
});
