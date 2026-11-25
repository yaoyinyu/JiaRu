/**
 * 甲面区域与真实指位的几何配对（纯逻辑）。
 *
 * 背景：识别模型只输出甲面框与掩膜，没有手性/指位信息；`inferSuggestedFingers`
 * 按候选数量给出 0..4 的占位值，实际落在候选**排名顺序**上。对手指方向与画面
 * x 轴不一致的图片（旋转、双手），排名顺序与真实指位无关，框上的指位标签因此
 * 会与最终应用的甲面不一致。
 *
 * 这里以手部关键点几何（每指一枚甲面参考）为准，用椭圆归一化距离做一一配对，
 * 再按指位去重，保证「画出的框」「标签」「应用到的指位」指向同一枚甲面。
 */

export interface FingerAssignmentRegion {
  id: string;
  cx: number;
  cy: number;
  nl: number;
  nw: number;
  angle: number;
  assignedFinger: number | null;
  confidence?: "high" | "medium" | "low";
}

export interface FingerAssignmentReference {
  id?: string;
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
  /** 参考自身的指位（0=拇指…4=小指）；无指位信息的参考会被忽略。 */
  finger: number | null;
}

export interface FingerGeometryMatch {
  regionId: string;
  referenceId: string | null;
  finger: number;
  /** 椭圆归一化距离平方；越小越贴合。 */
  cost: number;
}

export interface FingerGeometryAssignment<T extends FingerAssignmentRegion> {
  regions: T[];
  matches: FingerGeometryMatch[];
}

/**
 * 指尖补位：手部关键点给出了某根手指的甲面参考，但模型没在该处给出候选时，
 * 用参考几何补一个低置信区域（甲面漏检时用户仍能看到可微调的框）。
 */
export function appendRegionsForUnmatchedReferences<
  T extends FingerAssignmentRegion,
  R extends FingerAssignmentReference,
>(
  regions: readonly T[],
  references: readonly R[],
  create: (reference: R) => T,
  options: { maxCost?: number } = {}
): { regions: T[]; added: T[] } {
  const maxCost = options.maxCost ?? 0.9;
  const usable = references.filter(
    (reference) =>
      reference.finger != null &&
      [reference.cx, reference.cy, reference.length, reference.width, reference.angle].every(
        Number.isFinite
      ) &&
      reference.length > 4 &&
      reference.width > 3
  );
  const takenFingers = new Set(
    regions.map((region) => region.assignedFinger).filter((finger): finger is number => finger != null)
  );
  const added: T[] = [];
  for (const reference of usable) {
    const finger = reference.finger as number;
    if (takenFingers.has(finger)) continue;
    // 已有候选贴在该参考上：说明模型没漏，交给正常配对处理。
    const covered = regions.some(
      (region) => nailFingerTipCost(region, {
        finger,
        cx: reference.cx,
        cy: reference.cy,
        dirX: Math.sin(reference.angle),
        dirY: -Math.cos(reference.angle),
      }) <= maxCost
    );
    if (covered) continue;
    const region = create(reference);
    added.push(region);
    takenFingers.add(finger);
  }
  return { regions: added.length > 0 ? [...regions, ...added] : [...regions], added };
}

/**
 * 指尖支撑门：指尖参考可信时，与任何指尖都相差超过 `maxCost` 个甲长的候选
 * 按误检剔除（常见于衣物、纹理、甲根皮肤被模型当成甲面）。
 * 参考数量少于候选数量时不做剔除，避免把手部关键点没覆盖到的那只手整手删掉。
 */
export function filterRegionsByFingertipSupport<T extends FingerAssignmentRegion>(
  regions: readonly T[],
  tips: readonly FingerTipReference[],
  options: { maxCost?: number } = {}
): { regions: T[]; removed: T[] } {
  const maxCost = options.maxCost ?? 1.4;
  const usableTips = tips.filter(
    (tip) => tip.finger != null && [tip.cx, tip.cy].every(Number.isFinite)
  );
  if (usableTips.length < 3 || usableTips.length < regions.length) {
    return { regions: [...regions], removed: [] };
  }
  const kept: T[] = [];
  const removed: T[] = [];
  for (const region of regions) {
    const supported = usableTips.some(
      (tip) => nailFingerTipCost(region, tip) <= maxCost
    );
    if (supported) kept.push(region);
    else removed.push(region);
  }
  return removed.length > 0 ? { regions: kept, removed } : { regions: [...regions], removed: [] };
}

/** 手部几何参考 id 形如 `mediapipe-hand-1-finger-3`：尾码指位，末段前的数字为手序。 */
const REFERENCE_ID_PATTERN = /^mediapipe-hand-(\d+)-finger-(\d)$/;

export function parseHandReferenceId(
  id: string | undefined
): { handIndex: number; finger: number } | null {
  if (!id) return null;
  const match = REFERENCE_ID_PATTERN.exec(id);
  if (!match) return null;
  const handIndex = Number(match[1]);
  const finger = Number(match[2]);
  if (!Number.isInteger(handIndex) || !Number.isInteger(finger)) return null;
  if (finger < 0 || finger > 4) return null;
  return { handIndex, finger };
}

const DEFAULT_MAX_COST = 1.6;

function isFiniteRegion(region: FingerAssignmentRegion): boolean {
  return [region.cx, region.cy, region.nl, region.nw, region.angle].every(Number.isFinite)
    && region.nl > 0
    && region.nw > 0;
}

function isFiniteReference(reference: FingerAssignmentReference): boolean {
  return [reference.cx, reference.cy, reference.length, reference.width, reference.angle]
    .every(Number.isFinite)
    && reference.length > 0
    && reference.width > 0;
}

/**
 * 候选与手部几何参考的椭圆归一化距离平方。
 * 半轴取两者较大值，避免小参考把邻近甲面拉走。
 */
export function nailFingerMatchCost(
  region: FingerAssignmentRegion,
  reference: FingerAssignmentReference
): number {
  const dx = region.cx - reference.cx;
  const dy = region.cy - reference.cy;
  const cos = Math.cos(reference.angle);
  const sin = Math.sin(reference.angle);
  const across = Math.abs(dx * cos + dy * sin);
  const along = Math.abs(-dx * sin + dy * cos);
  const halfWidth = Math.max(region.nw, reference.width) * 0.5;
  const halfLength = Math.max(region.nl, reference.length) * 0.5;
  return (across / halfWidth) ** 2 + (along / halfLength) ** 2;
}

/**
 * 按手部几何为区域覆盖指位：贪心一一配对（代价低优先），
 * 同一参考只用一个候选，超出门限的候选保持原有指位不变。
 */
export function assignFingersFromHandGeometry<T extends FingerAssignmentRegion>(
  regions: readonly T[],
  references: readonly FingerAssignmentReference[],
  options: { maxCost?: number } = {}
): FingerGeometryAssignment<T> {
  const maxCost = options.maxCost ?? DEFAULT_MAX_COST;
  const usableReferences = references.filter(
    (reference) => reference.finger != null && isFiniteReference(reference)
  );

  interface Pair {
    regionIndex: number;
    referenceIndex: number;
    finger: number;
    cost: number;
  }

  const pairs: Pair[] = [];
  regions.forEach((region, regionIndex) => {
    if (!isFiniteRegion(region)) return;
    usableReferences.forEach((reference, referenceIndex) => {
      const cost = nailFingerMatchCost(region, reference);
      if (!Number.isFinite(cost) || cost > maxCost) return;
      pairs.push({ regionIndex, referenceIndex, finger: reference.finger as number, cost });
    });
  });

  pairs.sort((left, right) => {
    if (left.cost !== right.cost) return left.cost - right.cost;
    if (left.regionIndex !== right.regionIndex) return left.regionIndex - right.regionIndex;
    return left.referenceIndex - right.referenceIndex;
  });

  const usedRegions = new Set<number>();
  const usedReferences = new Set<number>();
  const matches: FingerGeometryMatch[] = [];
  const fingerByRegion = new Map<number, number>();

  for (const pair of pairs) {
    if (usedRegions.has(pair.regionIndex) || usedReferences.has(pair.referenceIndex)) continue;
    usedRegions.add(pair.regionIndex);
    usedReferences.add(pair.referenceIndex);
    fingerByRegion.set(pair.regionIndex, pair.finger);
    matches.push({
      regionId: regions[pair.regionIndex].id,
      referenceId: usableReferences[pair.referenceIndex].id ?? null,
      finger: pair.finger,
      cost: pair.cost,
    });
  }

  return {
    regions: regions.map((region, index) => {
      const finger = fingerByRegion.get(index);
      return finger == null ? { ...region } : { ...region, assignedFinger: finger };
    }),
    matches,
  };
}

export interface FingerTipReference {
  id?: string;
  finger: number | null;
  cx: number;
  cy: number;
  /** DIP→TIP 单位向量（远端方向）。 */
  dirX: number;
  dirY: number;
}

/**
 * 指尖参考到甲面中心距离，按甲面尺寸归一化（1 个甲长以内视为同一根手指）。
 * 指尖落点与甲面中心在侧转、弯指时会有偏移，因此只用一个甲长作为硬门限，
 * 由贪心唯一匹配挑最近的参考，避免把邻居手指的甲面拉过来。
 */
export function nailFingerTipCost(
  region: FingerAssignmentRegion,
  tip: FingerTipReference
): number {
  const scale = Math.max(region.nl, region.nw);
  if (!Number.isFinite(scale) || scale <= 0) return Number.POSITIVE_INFINITY;
  const dx = region.cx - tip.cx;
  const dy = region.cy - tip.cy;
  return (dx * dx + dy * dy) / (scale * scale);
}

/**
 * 用手部关键点指尖直接配对指位（不依赖手心/手背判定）。
 * 与几何配对一样做贪心一一匹配，超出门限的区域保持原指位。
 */
export function assignFingersFromFingerTips<T extends FingerAssignmentRegion>(
  regions: readonly T[],
  tips: readonly FingerTipReference[],
  options: { maxCost?: number } = {}
): FingerGeometryAssignment<T> {
  const maxCost = options.maxCost ?? 1;
  const usableTips = tips.filter(
    (tip) =>
      tip.finger != null &&
      [tip.cx, tip.cy, tip.dirX, tip.dirY].every(Number.isFinite)
  );

  interface Pair {
    regionIndex: number;
    tipIndex: number;
    finger: number;
    cost: number;
  }

  const pairs: Pair[] = [];
  regions.forEach((region, regionIndex) => {
    if (!isFiniteRegion(region)) return;
    usableTips.forEach((tip, tipIndex) => {
      const cost = nailFingerTipCost(region, tip);
      if (!Number.isFinite(cost) || cost > maxCost) return;
      pairs.push({ regionIndex, tipIndex, finger: tip.finger as number, cost });
    });
  });

  pairs.sort((left, right) => {
    if (left.cost !== right.cost) return left.cost - right.cost;
    if (left.regionIndex !== right.regionIndex) return left.regionIndex - right.regionIndex;
    return left.tipIndex - right.tipIndex;
  });

  const usedRegions = new Set<number>();
  const usedTips = new Set<number>();
  const matches: FingerGeometryMatch[] = [];
  const fingerByRegion = new Map<number, number>();

  for (const pair of pairs) {
    if (usedRegions.has(pair.regionIndex) || usedTips.has(pair.tipIndex)) continue;
    usedRegions.add(pair.regionIndex);
    usedTips.add(pair.tipIndex);
    fingerByRegion.set(pair.regionIndex, pair.finger);
    matches.push({
      regionId: regions[pair.regionIndex].id,
      referenceId: usableTips[pair.tipIndex].id ?? null,
      finger: pair.finger,
      cost: pair.cost,
    });
  }

  return {
    regions: regions.map((region, index) => {
      const finger = fingerByRegion.get(index);
      return finger == null ? { ...region } : { ...region, assignedFinger: finger };
    }),
    matches,
  };
}

const CONFIDENCE_ORDER: Record<NonNullable<FingerAssignmentRegion["confidence"]>, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

/**
 * 每个指位只保留一枚甲面：置信度高优先，同级保持原顺序。
 * 被移除的候选不再参与绘制与提取，避免「框在 A、纹理来自 B」。
 */
export function dedupeRegionsByFinger<T extends FingerAssignmentRegion>(
  regions: readonly T[]
): { regions: T[]; removed: T[] } {
  const keptByFinger = new Map<number, { index: number; region: T }>();
  const kept: T[] = [];
  const removed: T[] = [];

  regions.forEach((region, index) => {
    if (region.assignedFinger == null) {
      kept.push(region);
      return;
    }
    const existing = keptByFinger.get(region.assignedFinger);
    if (!existing) {
      keptByFinger.set(region.assignedFinger, { index, region });
      kept.push(region);
      return;
    }
    const existingRank = CONFIDENCE_ORDER[existing.region.confidence ?? "low"];
    const nextRank = CONFIDENCE_ORDER[region.confidence ?? "low"];
    if (nextRank < existingRank) {
      keptByFinger.set(region.assignedFinger, { index, region });
      removed.push(existing.region);
      const position = kept.indexOf(existing.region);
      if (position >= 0) kept[position] = region;
      return;
    }
    removed.push(region);
  });

  return { regions: kept, removed };
}
