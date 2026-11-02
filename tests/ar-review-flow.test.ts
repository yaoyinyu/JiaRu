import assert from "node:assert/strict";
import test from "node:test";

import {
  AR_STEPS,
  decideArReview,
  formatArApplyNotice,
  formatArReviewSummary,
  summarizeArReview,
} from "../src/lib/ar-review-flow.ts";

test("decideArReview 覆盖方案 §7.2 全部五条规则", () => {
  // 无旧纹理
  assert.equal(
    decideArReview({ hasExistingTexture: false, lowestConfidence: "high" }),
    "apply"
  );
  assert.equal(
    decideArReview({ hasExistingTexture: false, lowestConfidence: "medium" }),
    "apply_with_notice"
  );
  assert.equal(
    decideArReview({ hasExistingTexture: false, lowestConfidence: "low" }),
    "review"
  );
  // 有旧纹理
  assert.equal(
    decideArReview({ hasExistingTexture: true, lowestConfidence: "high" }),
    "replace_preview"
  );
  assert.equal(
    decideArReview({ hasExistingTexture: true, lowestConfidence: "medium" }),
    "confirm"
  );
  assert.equal(
    decideArReview({ hasExistingTexture: true, lowestConfidence: "low" }),
    "confirm"
  );
});

test("summarizeArReview 统计识别数/复核数/最低档", () => {
  const summary = summarizeArReview(["high", "low", "medium", "low"]);
  assert.equal(summary.recognizedCount, 4);
  assert.equal(summary.reviewCount, 2);
  assert.deepEqual(summary.reviewIndices, [1, 3]);
  assert.equal(summary.lowest, "low");

  const clean = summarizeArReview(["high", "high"]);
  assert.equal(clean.reviewCount, 0);
  assert.equal(clean.lowest, "high");

  const empty = summarizeArReview([]);
  assert.equal(empty.recognizedCount, 0);
  assert.equal(empty.lowest, null);
});

test("formatArReviewSummary 与 formatArApplyNotice 文案契约", () => {
  assert.equal(formatArReviewSummary({ recognizedCount: 0, reviewCount: 0 }), "未识别到甲面");
  assert.equal(
    formatArReviewSummary({ recognizedCount: 5, reviewCount: 0 }),
    "已识别 5 个甲面"
  );
  assert.equal(
    formatArReviewSummary({ recognizedCount: 5, reviewCount: 2 }),
    "已识别 5 个甲面，其中 2 个建议复核"
  );
  assert.equal(
    formatArApplyNotice({ appliedCount: 5, reviewCount: 2 }),
    "已自动提取并应用 5 指纹理，其中 2 指建议复核，可重新打开选择器调整。"
  );
  assert.equal(
    formatArApplyNotice({ appliedCount: 3, reviewCount: 0 }),
    "已自动提取并应用 3 指纹理，可重新打开选择器调整。"
  );
});

test("AR_STEPS 顶部步骤条三步顺序固定", () => {
  assert.deepEqual(
    AR_STEPS.map((step) => step.id),
    ["source", "extract", "tryon"]
  );
  assert.deepEqual(
    AR_STEPS.map((step) => step.label),
    ["选择来源", "提取与复核", "试戴与校准"]
  );
});
