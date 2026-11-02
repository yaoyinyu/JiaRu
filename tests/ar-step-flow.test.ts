import assert from "node:assert/strict";
import test from "node:test";

import {
  formatArReviewAppliedNotice,
  resolveArStepProgress,
} from "../src/lib/ar-step-flow.ts";

test("resolveArStepProgress 初始态停在 Step 1 选择来源", () => {
  const progress = resolveArStepProgress({
    hasAnyTexture: false,
    extractionActive: false,
    cameraActive: false,
  });
  assert.equal(progress.current, "source");
  assert.deepEqual(
    progress.steps.map((step) => step.status),
    ["active", "todo", "todo"]
  );
});

test("resolveArStepProgress 弹层 / 复核界面打开时进入 Step 2", () => {
  for (const extractionActive of [
    { showCropper: true, showPicker: false, review: false },
    { showCropper: false, showPicker: true, review: false },
    { showCropper: false, showPicker: false, review: true },
  ]) {
    const active = resolveArStepProgress({
      hasAnyTexture: false,
      extractionActive:
        extractionActive.showCropper || extractionActive.showPicker || extractionActive.review,
      cameraActive: false,
    });
    assert.equal(active.current, "extract");
    assert.equal(active.steps[0].status, "done");
    assert.equal(active.steps[1].status, "active");
    assert.equal(active.steps[2].status, "todo");
  }
});

test("resolveArStepProgress 摄像头运行或已有纹理时进入 Step 3", () => {
  const byCamera = resolveArStepProgress({
    hasAnyTexture: false,
    extractionActive: false,
    cameraActive: true,
  });
  assert.equal(byCamera.current, "tryon");
  assert.deepEqual(
    byCamera.steps.map((step) => step.status),
    ["done", "todo", "active"]
  );

  const byTexture = resolveArStepProgress({
    hasAnyTexture: true,
    extractionActive: false,
    cameraActive: false,
  });
  assert.equal(byTexture.current, "tryon");
  // 已产出纹理时 Step 2 记为完成
  assert.equal(byTexture.steps[1].status, "done");
  assert.equal(byTexture.steps[2].status, "active");
});

test("resolveArStepProgress 步骤标签与 ar-review-flow 的 AR_STEPS 一致", () => {
  const progress = resolveArStepProgress({
    hasAnyTexture: false,
    extractionActive: false,
    cameraActive: false,
  });
  assert.deepEqual(
    progress.steps.map((step) => step.id),
    ["source", "extract", "tryon"]
  );
  assert.deepEqual(progress.steps.map((step) => step.label), [
    "选择来源",
    "提取与复核",
    "试戴与校准",
  ]);
});

test("formatArReviewAppliedNotice 文案契约（应用后提供撤销提示）", () => {
  assert.equal(
    formatArReviewAppliedNotice({ appliedCount: 5, reviewCount: 2 }),
    "已应用 5 指纹理，其中 2 指建议复核，可撤销本次替换。"
  );
  assert.equal(
    formatArReviewAppliedNotice({ appliedCount: 3, reviewCount: 0 }),
    "已应用 3 指纹理，可撤销本次替换。"
  );
});
