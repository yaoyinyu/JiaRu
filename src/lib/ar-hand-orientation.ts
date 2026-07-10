export type HandOrientation = "dorsum" | "palm" | "ambiguous" | "none";

export interface HandOrientationPresentation {
  label: "手背" | "手心" | "侧手" | "";
  icon: "🖐️" | "✋" | "🤚" | "";
  tone: "dorsum" | "palm" | "neutral";
}

export interface HandOrientationDecision {
  orientation: "dorsum" | "palm" | "ambiguous";
  render: boolean;
  confidence: "high" | "low" | "none";
  reason: string;
  palmScore: number;
  dorsumScore: number;
}

export interface HandOrientationEvidence {
  palmDepthDiff: number;
  fingerDepthDiffs: readonly number[];
  /** (wrist -> index MCP) x (wrist -> pinky MCP), before display mirroring. */
  palmCrossZ: number;
  /** MediaPipe's original label for the unmirrored inference frame. */
  handedness: "Left" | "Right" | null;
}

const DEPTH_THRESHOLD = 0.003;
const STRONG_DEPTH_THRESHOLD = 0.008;
const SCORE_MARGIN = 2;
const CROSS_THRESHOLD = 0.002;
const STRONG_CROSS_THRESHOLD = 0.008;

/**
 * Classifies palm/back orientation from MediaPipe z-depth only.
 *
 * The previous x/y chirality signals were coupled to MediaPipe handedness and
 * could remain "palm" while a hand rotated. Symmetric z thresholds let both
 * orientations accumulate evidence under the same rules.
 */
export function classifyHandDepthOrientation(
  palmDepthDiff: number,
  fingerDepthDiffs: readonly number[],
): HandOrientationDecision {
  let palmScore = 0;
  let dorsumScore = 0;

  if (palmDepthDiff >= STRONG_DEPTH_THRESHOLD) palmScore += 3;
  else if (palmDepthDiff >= DEPTH_THRESHOLD) palmScore += 2;
  else if (palmDepthDiff <= -STRONG_DEPTH_THRESHOLD) dorsumScore += 3;
  else if (palmDepthDiff <= -DEPTH_THRESHOLD) dorsumScore += 2;

  for (const diff of fingerDepthDiffs) {
    if (diff >= DEPTH_THRESHOLD) palmScore += 1;
    else if (diff <= -DEPTH_THRESHOLD) dorsumScore += 1;
  }

  if (palmScore >= 2 && palmScore - dorsumScore >= SCORE_MARGIN) {
    return {
      orientation: "palm",
      render: false,
      confidence: palmScore >= 4 ? "high" : "low",
      reason: `手心深度证据 p${palmScore}/d${dorsumScore}`,
      palmScore,
      dorsumScore,
    };
  }

  if (dorsumScore >= 2 && dorsumScore - palmScore >= SCORE_MARGIN) {
    return {
      orientation: "dorsum",
      render: true,
      confidence: dorsumScore >= 4 ? "high" : "low",
      reason: `手背深度证据 d${dorsumScore}/p${palmScore}`,
      palmScore,
      dorsumScore,
    };
  }

  return {
    orientation: "ambiguous",
    render: true,
    confidence: "none",
    reason: `朝向证据不足 p${palmScore}/d${dorsumScore}`,
    palmScore,
    dorsumScore,
  };
}

/**
 * Normalizes palm topology so positive always means palm-facing and negative
 * always means dorsum-facing. The display is mirrored with CSS only, so this
 * must use MediaPipe's original handedness rather than the user-facing label.
 */
export function normalizePalmCrossForHandedness(
  palmCrossZ: number,
  handedness: HandOrientationEvidence["handedness"],
): number {
  if (handedness === "Right") return palmCrossZ;
  if (handedness === "Left") return -palmCrossZ;
  return 0;
}

/**
 * Classifies palm/back orientation using 2D palm topology as the primary
 * signal and z-depth as a fallback for near-sideways hands.
 *
 * MediaPipe relative z is useful for motion but can invert across camera,
 * lighting, and pose. The ordered wrist/index/pinky triangle does not have
 * that ambiguity while a hand is visibly palm- or dorsum-facing.
 */
export function classifyHandOrientation(
  evidence: HandOrientationEvidence,
): HandOrientationDecision {
  const normalizedCross = normalizePalmCrossForHandedness(
    evidence.palmCrossZ,
    evidence.handedness,
  );

  if (normalizedCross >= STRONG_CROSS_THRESHOLD) {
    return {
      orientation: "palm",
      render: false,
      confidence: "high",
      reason: `手心拓扑证据 c${normalizedCross.toFixed(4)}`,
      palmScore: 8,
      dorsumScore: 0,
    };
  }

  if (normalizedCross <= -STRONG_CROSS_THRESHOLD) {
    return {
      orientation: "dorsum",
      render: true,
      confidence: "high",
      reason: `手背拓扑证据 c${normalizedCross.toFixed(4)}`,
      palmScore: 0,
      dorsumScore: 8,
    };
  }

  const depthDecision = classifyHandDepthOrientation(
    evidence.palmDepthDiff,
    evidence.fingerDepthDiffs,
  );
  let palmScore = depthDecision.palmScore;
  let dorsumScore = depthDecision.dorsumScore;

  if (normalizedCross >= CROSS_THRESHOLD) palmScore += 4;
  else if (normalizedCross <= -CROSS_THRESHOLD) dorsumScore += 4;

  if (palmScore >= 3 && palmScore - dorsumScore >= SCORE_MARGIN) {
    return {
      orientation: "palm",
      render: false,
      confidence: palmScore >= 5 ? "high" : "low",
      reason: `手心融合证据 p${palmScore}/d${dorsumScore}`,
      palmScore,
      dorsumScore,
    };
  }

  if (dorsumScore >= 3 && dorsumScore - palmScore >= SCORE_MARGIN) {
    return {
      orientation: "dorsum",
      render: true,
      confidence: dorsumScore >= 5 ? "high" : "low",
      reason: `手背融合证据 d${dorsumScore}/p${palmScore}`,
      palmScore,
      dorsumScore,
    };
  }

  return {
    orientation: "ambiguous",
    render: true,
    confidence: "none",
    reason: `侧手/弱证据 c${normalizedCross.toFixed(4)} p${palmScore}/d${dorsumScore}`,
    palmScore,
    dorsumScore,
  };
}

/** Keeps detector semantics and user-facing labels aligned. */
export function getHandOrientationPresentation(
  orientation: HandOrientation,
): HandOrientationPresentation {
  switch (orientation) {
    case "dorsum":
      return { label: "手背", icon: "🖐️", tone: "dorsum" };
    case "palm":
      return { label: "手心", icon: "✋", tone: "palm" };
    case "ambiguous":
      return { label: "侧手", icon: "🤚", tone: "neutral" };
    default:
      return { label: "", icon: "", tone: "neutral" };
  }
}
