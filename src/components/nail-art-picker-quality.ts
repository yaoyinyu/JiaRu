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
    message: "Angle was stabilized from nearby candidates. Please confirm the orientation.",
  },
  angle_defaulted_vertical: {
    severity: "warning",
    message: "Angle was not stable enough and defaulted to vertical. Please adjust manually if needed.",
  },
  highlight_hotspots: {
    severity: "warning",
    message: "Strong highlights may reduce visible texture detail.",
  },
  dirty_mask_crop: {
    severity: "warning",
    message: "The crop appears to include too much non-nail content. Please review the boundary.",
  },
  mask_crop_touches_edge: {
    severity: "warning",
    message: "The crop touches the edge and may be missing part of the nail.",
  },
  mask_foreground_too_small: {
    severity: "warning",
    message: "The usable nail area looks small and may reduce texture quality.",
  },
  mask_has_no_foreground_pixels: {
    severity: "warning",
    message: "No valid foreground pixels were extracted from the mask. Please refine the region.",
  },
  mediapipe_geometry_detection: {
    severity: "info",
    message: "This result mostly comes from geometric estimation. A manual review is recommended.",
  },
};

const RECOGNITION_WARNING_MESSAGES: Record<string, string> = {
  no_candidates_detected: "No usable nail candidates were detected.",
  worker_unavailable_used_main_thread: "Worker is unavailable, so detection ran on the main thread.",
  model_runtime_unavailable_on_server: "The current environment cannot load the model runtime directly.",
  no_supported_model_backend: "The browser does not support a usable model backend, so detection fell back to rules.",
  onnx_runtime_not_loaded: "The model runtime was not ready, so detection fell back to rules.",
  onnx_session_init_failed: "The model session failed to initialize, so detection fell back to rules.",
  recognition_cancelled_by_user: "Auto detection was cancelled. You can continue by adding regions manually.",
};

function dedupeMessages(messages: string[]): string[] {
  return [...new Set(messages.filter(Boolean))];
}

export function presentCandidateWarning(warning: string): NailArtPickerWarningPresentation {
  return (
    CANDIDATE_WARNING_MESSAGES[warning] ?? {
      severity: "warning",
      message: `闂傚倷鑳堕…鍫ユ晝閵夆晜鍋￠柍鍝勬噹閻掑灚銇勯幒鍡椾壕濡炪倧闄勬刊浠嬪Φ閹邦厽濯撮柧蹇撴贡閻掑ジ姊虹紒妯垮妞ゆ洦鍘剧划?{warning}`,
    }
  );
}

export function presentRecognitionWarning(warning: string): string {
  return RECOGNITION_WARNING_MESSAGES[warning] ?? `Recognition warning: ${warning}`;
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
    `Quality: ${quality.ok ? "ok" : "review"}`,
    `Highlight pixels: ${highlightRepair.highlightPixels}`,
    `Repaired pixels: ${highlightRepair.repairedPixels}`,
  ];

  const messages: string[] = [];
  for (const warning of quality.warnings) {
    messages.push(presentCandidateWarning(warning).message);
  }

  if (highlightRepair.highlightPixels > 0) {
    messages.push(
      highlightRepair.repairedPixels > 0
        ? "Highlights were detected and some pixels were repaired."
        : "Highlights were detected, but there was not enough nearby texture to repair them."
    );
  }

  return {
    severity: quality.ok && highlightRepair.highlightPixels === 0 ? "ok" : "review",
    title:
      quality.ok && highlightRepair.highlightPixels === 0
        ? "The current texture extraction looks stable"
        : "The current texture extraction should be reviewed",
    stats,
    messages: dedupeMessages(messages),
  };
}

export function summarizeRegionQuality(
  region: NailArtPickerQualityRegionLike
): NailArtPickerRegionQualitySummary {
  const messages: string[] = [];

  if (region.confidence === "low") {
    messages.push("This candidate has low confidence. Please review its position, angle, and size.");
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
        title: "Please review the current candidate",
        messages: deduped,
      }
    : {
        severity: "ok",
        title: "The current candidate looks good",
        messages: [],
      };
}