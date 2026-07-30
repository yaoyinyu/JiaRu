import {
  computeNailGeometry,
  NAIL_DIPS,
  NAIL_PIPS,
  NAIL_TIPS,
  type NailLandmark,
} from "./nail-geometry.ts";
import { classifyHandOrientation } from "./ar-hand-orientation.ts";
import { resolveMediaPipeHandsAsset } from "./mediapipe-hands-assets.ts";
import type { NailTextureCandidate } from "./nail-texture-recognition/types.ts";

export interface HandGeometryDetectionInput {
  multiHandLandmarks?: readonly (readonly NailLandmark[])[];
  multiHandedness?: readonly {
    label: "Left" | "Right";
    score: number;
  }[];
}

export interface HandGeometryDetectionResult {
  candidates: NailTextureCandidate[];
  warnings: string[];
}

function createAbortError(): DOMException {
  return new DOMException("手部自动定位已取消", "AbortError");
}

function fingerExtensionAngle(
  pip: NailLandmark,
  dip: NailLandmark,
  tip: NailLandmark
): number {
  const firstX = dip.x - pip.x;
  const firstY = dip.y - pip.y;
  const secondX = tip.x - dip.x;
  const secondY = tip.y - dip.y;
  return Math.abs(
    Math.atan2(firstX * secondY - firstY * secondX, firstX * secondX + firstY * secondY)
  );
}

export function createNailCandidatesFromHandGeometry(
  input: HandGeometryDetectionInput,
  imageWidth: number,
  imageHeight: number
): HandGeometryDetectionResult {
  const hand = input.multiHandLandmarks?.[0];
  if (!hand || hand.length < 21) {
    return { candidates: [], warnings: ["mediapipe_no_hand_detected"] };
  }

  const handedness = input.multiHandedness?.[0] ?? null;
  const wrist = hand[0];
  const indexMcp = hand[5];
  const pinkyMcp = hand[17];
  const palmCrossZ =
    (indexMcp.x - wrist.x) * (pinkyMcp.y - wrist.y) -
    (indexMcp.y - wrist.y) * (pinkyMcp.x - wrist.x);
  const palmDepth =
    ((hand[0].z ?? 0) + (hand[5].z ?? 0) + (hand[9].z ?? 0) + (hand[17].z ?? 0)) / 4;
  const knuckleDepth =
    ((hand[2].z ?? 0) +
      (hand[6].z ?? 0) +
      (hand[10].z ?? 0) +
      (hand[14].z ?? 0) +
      (hand[18].z ?? 0)) /
    5;
  const decision = classifyHandOrientation({
    palmDepthDiff: palmDepth - knuckleDepth,
    fingerDepthDiffs: [1, 2, 3, 4].map(
      (finger) => (hand[NAIL_TIPS[finger]].z ?? 0) - (hand[NAIL_PIPS[finger]].z ?? 0)
    ),
    palmCrossZ,
    handedness: handedness?.label ?? null,
  });

  if (decision.orientation === "palm" && decision.confidence === "high") {
    return { candidates: [], warnings: ["mediapipe_palm_facing"] };
  }

  const candidates: NailTextureCandidate[] = [];
  for (let finger = 0; finger < 5; finger += 1) {
    const tip = hand[NAIL_TIPS[finger]];
    const dip = hand[NAIL_DIPS[finger]];
    const pip = hand[NAIL_PIPS[finger]];
    if (!tip || !dip || !pip) continue;

    // 严重弯折的手指通常只露出侧面，自动框不应把整段指腹当作甲面。
    if (fingerExtensionAngle(pip, dip, tip) > Math.PI * 0.42) continue;

    const geometry = computeNailGeometry(hand, finger, imageWidth, imageHeight);
    if (!geometry || geometry.length < 8 || geometry.width < 6) continue;

    candidates.push({
      id: `mediapipe-hand-0-finger-${finger}`,
      ...geometry,
      score: handedness?.score ?? 0.7,
      confidence:
        decision.orientation === "dorsum" && decision.confidence === "high"
          ? "medium"
          : "low",
      source: "mediapipe",
      suggestedFinger: finger,
      warnings: [
        "mediapipe_geometry_detection",
        ...(decision.orientation === "ambiguous" ? ["mediapipe_orientation_ambiguous"] : []),
      ],
    });
  }

  return {
    candidates,
    warnings:
      candidates.length > 0
        ? ["model_unavailable_used_mediapipe_geometry"]
        : ["mediapipe_no_nail_geometry"],
  };
}

export async function detectNailsFromHandImage(
  image: HTMLImageElement,
  options: { signal?: AbortSignal; timeoutMs?: number } = {}
): Promise<HandGeometryDetectionResult> {
  if (options.signal?.aborted) throw createAbortError();
  const timeoutMs = options.timeoutMs ?? 20_000;
  const { Hands } = await import("@mediapipe/hands");
  const hands = new Hands({
    locateFile: resolveMediaPipeHandsAsset,
  });
  hands.setOptions({
    selfieMode: false,
    maxNumHands: 1,
    modelComplexity: 1,
    minDetectionConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });

  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let abortHandler: (() => void) | undefined;
  try {
    const results = await new Promise<HandGeometryDetectionInput>((resolve, reject) => {
      let settled = false;
      const finish = (callback: () => void) => {
        if (settled) return;
        settled = true;
        callback();
      };
      hands.onResults((result) => finish(() => resolve(result)));
      abortHandler = () => finish(() => reject(createAbortError()));
      options.signal?.addEventListener("abort", abortHandler, { once: true });
      timeoutId = setTimeout(
        () => finish(() => reject(new Error("mediapipe_hand_detection_timeout"))),
        timeoutMs
      );
      void hands
        .initialize()
        .then(() => hands.send({ image }))
        .catch((reason) => finish(() => reject(reason)));
    });

    return createNailCandidatesFromHandGeometry(
      results,
      image.naturalWidth,
      image.naturalHeight
    );
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    if (abortHandler) options.signal?.removeEventListener("abort", abortHandler);
    await hands.close().catch(() => undefined);
  }
}
