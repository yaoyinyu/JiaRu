import type { TextureExtractionDiagnostics } from "@/lib/nail-texture-recognition";

export interface NailArtPickerQualityRegionLike {
  confidence?: "high" | "medium" | "low";
  warnings?: string[];
  extractionDiagnostics?: TextureExtractionDiagnostics;
}

export interface NailArtPickerWarningPresentation {
  severity: "info" | "warning";
  message: string;
}

export interface NailArtPickerRegionQualitySummary {
  severity: "ok" | "review";
  title: string;
  messages: string[];
}

export interface NailArtPickerExtractionDiagnosticsSummary {
  severity: "ok" | "review";
  title: string;
  stats: string[];
  messages: string[];
}

const CANDIDATE_WARNING_MESSAGES: Record<string, NailArtPickerWarningPresentation> = {
  angle_stabilized_from_group: {
    severity: "info",
    message: "候选方向已参考附近甲面做稳定化，建议确认朝向是否正确。",
  },
  angle_defaulted_vertical: {
    severity: "warning",
    message: "候选方向不够稳定，已回退为竖直方向，建议手动调整。",
  },
  highlight_hotspots: {
    severity: "warning",
    message: "甲面高光较强，可能影响纹理细节。",
  },
  dirty_mask_crop: {
    severity: "warning",
    message: "裁剪区域混入了较多非甲面像素，建议检查边界。",
  },
  mask_crop_touches_edge: {
    severity: "warning",
    message: "裁剪区域贴边，可能缺失部分甲面。",
  },
  mask_foreground_too_small: {
    severity: "warning",
    message: "可用甲面区域偏小，可能影响纹理质量。",
  },
  mask_has_no_foreground_pixels: {
    severity: "warning",
    message: "当前 mask 没有提取到有效甲面像素，建议重新调整。",
  },
  mediapipe_geometry_detection: {
    severity: "info",
    message: "该候选主要来自几何估计，建议人工复核。",
  },
};

const RECOGNITION_WARNING_MESSAGES: Record<string, string> = {
  no_candidates_detected: "没有检测到可用的美甲候选区域。",
  worker_unavailable_used_main_thread: "当前环境未启用 Worker，已回退到主线程识别。",
  model_runtime_unavailable_on_server: "当前环境无法直接加载模型运行时，已回退到规则识别。",
  no_supported_model_backend: "浏览器没有可用的模型推理后端，已回退到规则识别。",
  onnx_runtime_not_loaded: "模型运行时尚未就绪，已回退到规则识别。",
  onnx_session_init_failed: "模型会话初始化失败，已回退到规则识别。",
  recognition_cancelled_by_user: "自动识别已取消，你可以继续手动添加和调整区域。",
};

const RECOGNITION_WARNING_PREFIX_MESSAGES: Array<[prefix: string, message: string]> = [
  ["model_manifest_error", "模型清单加载或校验失败，已回退到规则识别。"],
  ["model_inference_error", "模型推理运行失败，已回退到规则识别。"],
  ["onnx_session_init_failed", "模型会话初始化失败，已回退到规则识别。"],
  ["onnx_session_or_tensor_unavailable", "模型会话或张量接口不可用，已回退到规则识别。"],
  ["model_outputs_empty_used_fallback", "模型没有输出可用候选，已回退到规则识别。"],
];
function dedupeMessages(messages: string[]): string[] {
  return [...new Set(messages.filter(Boolean))];
}

export function presentCandidateWarning(warning: string): NailArtPickerWarningPresentation {
  return (
    CANDIDATE_WARNING_MESSAGES[warning] ?? {
      severity: "warning",
      message: `候选存在未分类问题：${warning}`,
    }
  );
}

export function presentRecognitionWarning(warning: string): string {
  const exactMessage = RECOGNITION_WARNING_MESSAGES[warning];
  if (exactMessage) return exactMessage;

  const prefixMessage = RECOGNITION_WARNING_PREFIX_MESSAGES.find(([prefix]) =>
    warning.startsWith(prefix)
  )?.[1];
  return prefixMessage ?? `识别提示：${warning}`;
}

export function regionNeedsReview(region: NailArtPickerQualityRegionLike): boolean {
  if (region.confidence === "low") return true;
  if ((region.warnings?.length ?? 0) > 0) return true;
  return Boolean(region.extractionDiagnostics && !region.extractionDiagnostics.quality.ok);
}

export function summarizeExtractionDiagnostics(
  diagnostics?: TextureExtractionDiagnostics
): NailArtPickerExtractionDiagnosticsSummary | null {
  if (!diagnostics) return null;

  const { quality, highlightRepair } = diagnostics;
  const stats = [
    `质量：${quality.ok ? "正常" : "需复核"}`,
    `高光像素：${highlightRepair.highlightPixels}`,
    `已修复：${highlightRepair.repairedPixels}`,
  ];

  const messages: string[] = [];
  for (const warning of quality.warnings) {
    messages.push(presentCandidateWarning(warning).message);
  }

  if (highlightRepair.highlightPixels > 0) {
    messages.push(
      highlightRepair.repairedPixels > 0
        ? "检测到高光区域，已对可修复部分做轻微修复。"
        : "检测到高光区域，但周边可参考纹理不足，暂未完成修复。"
    );
  }

  return {
    severity: quality.ok && highlightRepair.highlightPixels === 0 ? "ok" : "review",
    title:
      quality.ok && highlightRepair.highlightPixels === 0
        ? "当前纹理提取结果稳定"
        : "当前纹理提取结果建议复核",
    stats,
    messages: dedupeMessages(messages),
  };
}

export function summarizeRegionQuality(
  region: NailArtPickerQualityRegionLike
): NailArtPickerRegionQualitySummary {
  const messages: string[] = [];

  if (region.confidence === "low") {
    messages.push("当前候选置信度偏低，建议检查位置、角度和大小。");
  }

  for (const warning of region.warnings ?? []) {
    messages.push(presentCandidateWarning(warning).message);
  }

  if (region.extractionDiagnostics && !region.extractionDiagnostics.quality.ok) {
    for (const warning of region.extractionDiagnostics.quality.warnings) {
      messages.push(presentCandidateWarning(warning).message);
    }
  }

  const deduped = dedupeMessages(messages);
  return deduped.length
    ? {
        severity: "review",
        title: "建议复核当前候选",
        messages: deduped,
      }
    : {
        severity: "ok",
        title: "当前候选状态良好",
        messages: [],
      };
}
