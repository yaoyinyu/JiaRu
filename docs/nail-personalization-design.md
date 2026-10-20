# 个性化美甲分析推荐 · 功能设计技术文档

> 设计日期：2026-10-19；2026-10-20 文档级复核后修订（契约、规则表、测试计划与文档自洽，修订清单见 §12）。
> 配套资料汇编：`docs/nail-personalization-research.md`（规则来源、竞品与学术依据，引用编号 [Sxx] 均指该文档；其中 §2.5 为争议/失效/不可迁移证据，§9 为检索方法与维护说明）。
> **文档边界澄清（修正原表述歧义）**：本文档本身不属于白皮书正文，因此**本轮文档修订不顺延白皮书版本号**；功能代码落地轮才按白皮书 §12 模板登记（§3 状态行 + §4.x 小节），并按**落地当时的白皮书头部版本顺延一位**——原写死的「v1.2.133 → v1.2.134」已改为动态口径，见 §9。

---

## 1. 目标、范围与边界

**目标**：用户在 JiaRu 内上传/拍摄一张手背照片，系统在浏览器本地完成甲面候选识别，基于**甲型（甲床几何）、手型（甲面派生比例）、皮肤质量（肤色与底调 / 手部皮肤 / 指甲健康三通道）、应用场景与个人身份（问卷）**做个性化分析，输出可解释的美甲推荐（甲型 + 长度 + 色系 + 「为什么适合」），并可一键带入编辑器预涂。

**v1 边界（硬约束）**：
1. **纯规则引擎 + 现有管线输出**：不引入任何新模型训练、不新增 ONNX、不改识别链路——与纹理模型训练 Goal 的「唯一活动里程碑」零冲突（禁改清单见 §9）。
2. 肤色只测**深浅与底调**（ITA°/Lab），不判「美丑」、不输出肤质评分营销话术；手部皮肤质量维度以「采样质量 + 光照可控性提示」呈现，不做皮肤病变检测。
3. 指甲健康只做三类启发式观察（颜色均匀度/高光占比/生长轴纹理条纹），**不做任何疾病分类**（学术上的疾病检测均需训练模型 [S32][S34][S37]，明确排除）；输出恒带非医疗声明。
4. 输出定位为「可解释的启发式建议」，卡片必带解释与置信度；识别后端为 fallback 或候选低置信时，必须如实标注「辅助结果未经正式模型确认」（见 §8）。

---

## 2. 总体架构与数据流

```text
用户上传照片（src/lib/image-upload-validation.ts 复用：MIME 三选一/≤10MB/320–4096px）
  → canvas 降采样至最长边 ≤800（与 NailArtPicker 的 MAX_DETECTION_DIM 一致，保证候选可比）
  → recognizeNailTexturesInWorker（src/lib/nail-texture-recognition，直连先例：device-benchmark）
  → remapNailTextureCandidatesToOriginal（input-scaling.ts）回原图坐标
  → 三路纯函数分析（src/lib/nail-personalization/）：
      ① hand-profile.ts    甲床长宽比/相对宽度/手型四分类（仅用候选 length/width/suggestedFinger）
      ② skin-sampling.ts   甲周肤色环采样 → color-science.ts（Lab/ITA°/Monk 近似/底调）
      ③ nail-health.ts     指甲健康启发式（仅用带 mask 候选；无 mask → null）
  → rules.ts 规则引擎（+ UserScenario 问卷：场合/风格/劳作强度/长度偏好/自评底调）
  → present.ts 中文解释文案（复刻 nail-art-picker-quality.ts 纯函数模式）
  → 推荐卡片 UI（NailAnalysisResult.tsx）+ PRODUCT HOLD 琥珀边界
  → bridge.ts 出站 → /editor?preset=<色名>（照 ?gallery= 参数桥接先例）
```

**新页面选择：独立路由 `/nail-analysis`，不并入 NailArtPicker。** 理由：①NailArtPicker（1,115 行）职责是「识别→逐指确认→提取」，叠加问卷+推荐会混淆两条产品路径；②肤色环采样需要原分辨率像素（识别输入最长边 800），独立页面自持 `<img>` 原图，无需向模态框钻取 props；③device-benchmark 已证明新页面可直连识别库，回归面最小；④「候选未经人工确认」的琥珀边界可做成页面级固定声明，比塞进模态框更如实；⑤出站用既有参数桥接模式，反向不依赖 ar-tryon 改动。

---

## 3. 模块划分与契约（`src/lib/nail-personalization/`）

全部模块为**无 DOM 依赖纯函数**（像素以 `ImagePixels` 传入），Node 测试环境可直接运行——与 `gallery-inspiration.ts`、`nail-art-picker-quality.ts` 同一模式。类型来源：`NailTextureCandidate`/`NailMask` 引自 `../nail-texture-recognition/types.ts`，`ImagePixels` 引自 `../nail-image-detection.ts`。

### 3.1 types.ts（共享类型）

```ts
export type FingerIndex = 0 | 1 | 2 | 3 | 4; // 与 suggestedFinger 一致
export type HandShapeClass = "narrow-long" | "wide-short" | "slim-tapered" | "balanced";
export type ItaBand = "very-light" | "light" | "intermediate" | "tan" | "brown" | "dark";
export type MonkGrade = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;
export type Undertone = "warm" | "cool" | "neutral" | "olive";
export type Occasion = "work" | "party" | "wedding" | "date" | "vacation" | "daily";
export type StylePreference = "low-maintenance" | "natural" | "bold" | "elegant" | "trendy";
export type ManualLabor = "none" | "light" | "heavy";
export type LengthAdvice = "short" | "medium" | "long";
export type NailShapeAdvice = "round" | "squoval" | "square" | "oval" | "almond" | "coffin" | "stiletto";

export interface NailBedMetrics { finger: FingerIndex; lengthPx: number; widthPx: number; aspectRatio: number; relativeWidth: number; }
export interface HandProfile {
  shape: HandShapeClass;
  palmAspect: number | null;      // 手轴坐标系下的掌心跨度近似（候选不含掌部 landmarks，为近似量；已按候选 angle 中位数旋转归一化，见 §3.4）
  thumbRatio: number | null;      // 拇指甲宽 / 其余甲最大宽
  nailBeds: NailBedMetrics[];
  medianNailAspect: number;       // 五甲长宽比中位数
  completeness: number;           // 0~1（可用候选数/5，带 mask 与 suggestedFinger 加权）
  warnings: string[];
}

export interface SkinToneAnalysis {
  lab: { L: number; a: number; b: number };  // 甲周环聚合（逐通道中位数）的 CIELAB
  ita: number; itaBand: ItaBand; monkGrade: MonkGrade;
  undertone: Undertone; undertoneSource: "measured" | "self-reported";
  sampleCount: number; quality: number;      // quality 0~1：皮肤像素占比 × 候选覆盖
  warnings: string[];
}

export interface NailHealthHeuristic {
  score: number;                 // 0~100 启发式
  colorUniformity: number;       // 0~1（mask 前景 L* 的 MAD 归一化）
  highlightRatio: number;        // 0~1（复用 extract-mask-texture.ts 同款高光定义）
  textureStreaking: number;      // 0~1（沿甲长轴梯度 / 垂直轴梯度）
  warnings: string[]; heuristicOnly: true;   // 恒定 true：仅启发式观察，不构成医疗或诊断结论
}

export interface UserScenario {
  occasion: Occasion; style?: StylePreference; manualLabor?: ManualLabor;
  lengthPreference?: LengthAdvice; selfReportedUndertone?: Undertone; // 自评优先，来源标记 self-reported
  nailCondition?: NailCondition;   // 甲面状况自评（对齐资料汇编 §3.4「指甲薄软先加固」与 §8 结论）
  hasAllergyHistory?: boolean;     // 仅触发安全提示，不参与推荐打分（材料化学安全性超出 v1 范围）
}

export type NailCondition = "healthy" | "thin-soft" | "brittle" | "unknown";

/**
 * 三态语义（规则实现必须遵守，见 §3.6 规则表注 2）：
 * 所有 optional 字段（style/manualLabor/lengthPreference/selfReportedUndertone/nailCondition）
 * 的「未填」一律表示 unknown，**严禁把 undefined 当作否定值参与条件判断**；
 * `x !== "long"` 之类的写法在 undefined 下恒为 true，属已知语义缺陷。
 */

export interface ColorAdvice { family: string; presetNames: string[]; season?: "spring" | "summer" | "autumn" | "winter"; }
export interface RecommendationExplanation { ruleId: string; message: string; severity: "info" | "warning"; }
export interface Recommendation {
  id: string;   // 确定性派生：`${shape}-${length}-${colors.family}`，同一输入必得同一 id（黄金测试逐字断言的前提）
  rank: number; score: number;
  shape: NailShapeAdvice; length: LengthAdvice; colors: ColorAdvice;
  explanations: RecommendationExplanation[];
  confidence: "high" | "medium" | "low";
  requiresManualConfirmation: boolean;  // fallback/低置信/输入不足时为 true，UI 必须呈现琥珀提示
  ruleHits: string[];                   // 黄金测试锚点
}

/**
 * 原图像素标记类型：肤色采样与健康启发式必须吃**原分辨率**像素。
 * 识别用的降采样图（最长边 ≤800）与它同为 ImagePixels 结构，类型层无法区分，
 * 因此用交叉类型强制调用方显式声明，防止误把 800 图当原图采样（该错误不可由测试稳定捕获）。
 */
export type OriginalImagePixels = ImagePixels & { readonly pixelSource: "original" };

export interface PersonalizationInput {
  image: OriginalImagePixels;               // 原图像素（肤色采样与健康启发式），禁止传入降采样图
  candidates: readonly NailTextureCandidate[]; // 已回原图坐标
  backend: "model" | "fallback";            // PRODUCT HOLD 边界判定
  scenario: UserScenario;
  maxCandidates?: number;                   // 期望候选数（默认 5），用于 completeness 与 skin quality 分母
}
export interface PersonalizationResult {
  handProfile: HandProfile;
  skinTone: SkinToneAnalysis | null;   // 采样质量不足 → null（隐藏而非猜测）
  nailHealth: NailHealthHeuristic | null; // 无 mask 候选 → null
  recommendations: Recommendation[];
  notices: string[];                   // 页面级提示（琥珀辅助定位声明等）
}
```

### 3.2 color-science.ts（色彩科学）

```ts
export function rgbToLab(r: number, g: number, b: number): { L: number; a: number; b: number };
export function individualTypologyAngle(lab: { L: number; a: number; b: number }): number; // arctan((L*-50)/b*)×180/π
export function classifyItaBand(ita: number): ItaBand;
export function approximateMonkGrade(lab: { L: number; a: number; b: number }): MonkGrade;
export function classifyUndertone(lab: { L: number; a: number; b: number }): Undertone;
export function labDistance(a: Lab, b: Lab): number; // ΔE76
```

实现要点：
- sRGB → XYZ（D65 白点）→ Lab 全流程；阈值常量集中在文件顶部，便于运营调整与测试锁定。
- **分档边界开闭（2026-10-20 明确；原文档缺失导致实现必然漂移）**：`ITA_BAND_BOUNDS = [55, 41, 28, 10, -30]`，统一采用**左开右闭**——`ita > 55` → very-light；`41 < ita ≤ 55` → light；`28 < ita ≤ 41` → intermediate；`10 < ita ≤ 28` → tan；`-30 < ita ≤ 10` → brown；`ita ≤ -30` → dark。测试须逐档断言边界值归属（55→light、41→intermediate、28→tan、10→brown、−30→dark）。
- **分档可靠性与规则弃权（2026-10-20 第二轮新增，源自跨光照一致性实证）**：`classifyItaBandStable()` 在两种情况下返回 `reliable=false`——①`|b*| < ITA_UNSTABLE_B_ABS(4)`：ITA° 分母趋零、atan 饱和到 ±90，分档改由 b\* 符号决定（实测 `b*=−0.25`→dark、`b*=+0.25`→very-light，**0.5 的 b\* 变化即在最浅与最深档之间翻转**）；②`|ITA° − 任一边界| < ITA_BOUNDARY_MARGIN(3)`：实测同色温照度每降 10% 移一档、仅更换光源色温即可跨过 55 边界。`reliable=false` 时 `SkinToneAnalysis.itaReliable=false` 并带 `itaUncertainty` 原因，**全部消费 ITA° 分档或底调的颜色规则一律弃权**（见 §3.6 规则表注 5），颜色建议回落场合/风格/甲面状况规则，肤色摘要降级为 review 并明示「本次颜色建议未按肤色深浅给出」。两个阈值为预注册假设，标定要求见 §8。该机制不改动任何几何与问卷驱动的建议，也**不引入任何光照归一化**——亮度/曝光归一化会摧毁 ITA° 所要测量的深浅信号，整图白平衡在皮肤主导画面中无可靠参考白，两者均明确不做。
- ITA° 公式依据 [S80]（1991 原始定义，经 [S38][S39] 转引）与 [S38]（同行评审）。**注意**：ITA° 建立在受控测量条件（标准光源、无病变/无阴影区域）下，非受控手机拍照的绝对值不等于文献口径（资料汇编 §2.5 第 3 条）。
- `approximateMonkGrade`：**口径修正（对齐资料汇编 §8 第 2 条）**——[S38] 的 Monk 映射是 **ITA° → Monk**，不是 L\* → Monk。v1 采用 ITA° 分档映射表 `MONK_ITA_BOUNDS`（常量置于文件顶部，取值由测试锁定）。若因实现便利改用 L\* 线性近似（1≈L\*80 … 10≈L\*28），**必须在文件头部注释声明「该 L\* 近似无来源支持，仅供色号筛选沟通，不是标准 Monk 评估」**，且 UI 不得称其为 Monk 等级。Monk 标度为十级开源肤色标度 [S40]；**不输出 Fitzpatrick**（资料汇编 §2.5 第 2 条）。
- `classifyUndertone`：**优先级与边界（2026-10-20 明确，原规则存在判定空洞）**，按序判定、命中即返回：① 橄榄：`a* > UNDERTONE_OLIVE_A(2)` 且 `b* ≥ UNDERTONE_COOL_B_LOW(4)`；② 暖：`b* > 14`；③ 冷：`b* < 4` 且 `a* < 0`；④ 其余 `neutral`。即**橄榄优先于暖**（`a* > 2` 且 `b* > 14` 亦判 olive，消除原规则的优先级空洞），b\* 下界量化为 4（不设上界，否则 `a*>2 且 b*>14` 会落回 warm 而违背「橄榄优先」）。实现已同步，见 `color-science.ts` 与对应测试。方法学依据底调理论 [S54][S60] 与 Lab 通道语义 [S38]；**输出必须允许用户自评覆盖**（问卷 `selfReportedUndertone`），因为非受控拍照下底调测量不可靠 [S39][S81]。

### 3.3 skin-sampling.ts（甲周肤色环采样）

```ts
export interface PeriNailSample { lab: { L: number; a: number; b: number }; sampleCount: number; quality: number; warnings: string[]; }
export function samplePeriNailSkin(
  image: ImagePixels,
  candidates: readonly NailTextureCandidate[],
  options?: { ringScale?: number } // 默认内环 1.15×、外环 1.6× 甲面椭圆半轴
): PeriNailSample;
```

算法：
1. 对每个候选在其局部坐标系（cx/cy/length/width/angle）取椭圆环采样点：24 角向 × 3 径向（内 1.15×/中 1.35×/外 1.6× 半轴）；
2. 肤色判定用**放宽版** YCbCr/RGB 规则——错误像素由逐通道**中位数**聚合吸收；
3. 有 `mask` 的候选按 mask 膨胀环取点；无 mask（mediapipe/局部近景路径）按候选椭圆几何取点；
4. **甲面自污染排除（2026-10-20 新增；原算法缺失该判据）**：采样点满足以下任一条件必须剔除，且**不计入皮肤像素、也不计入分母**——①落在任一候选的甲面椭圆内部（膨胀前的原始半轴，含自身候选）；②与任一候选中心距离 < 该候选半长轴 × 1.0（邻甲安全距离）；③落在图像边界外。理由：无 mask 的 fallback 候选几何不准，环采样极易采到甲面本身或邻甲，会把甲色当成肤色，且该错误会被中位数聚合掩盖。
5. 仅迭代候选包围盒，不扫全图；性能预算见 §7 性能用例——**<50ms 仅指采样循环本身，不含原图 `getImageData`、解码与 ImageBitmap 创建**。
6. **quality 门改为双条件（2026-10-20 修正；原单条件无可证伪标定）**：`quality = 皮肤像素占比 × (有效候选数 / 期望候选数)`，且必须**同时**满足绝对下限 `skinSampleCount >= MIN_SKIN_SAMPLES`（默认 120 ≈ 24 角向 × 3 径向 × 2 个有效候选；仅 1 个有效候选时下限取 60）。`quality < 0.35` **或** `skinSampleCount < MIN_SKIN_SAMPLES` 时，上游置 `skinTone = null` 并出 `skin_sampling_low_quality` 警告——**不允许低质量采样冒充测量结果**。注：`0.35` 与 `120` 均为**预注册假设而非标定值**，标定要求见 §8 M3。

**实现约束（2026-10-20 源码核实后修正）**：`src/lib/nail-partial-closeup-detection.ts` 只导出 `assignPartialCloseupCandidateFingers`、`detectPartialCloseupNails`、`detectPartialCloseupNailCandidates` 三个函数，**没有可 import 的肤色规则 helper**。因此"复用"只能是把其阈值常量**复制到 skin-sampling.ts 内重新实现**，属规则漂移风险点，必须：①在本文件注明常量来源文件与复制日期；②在 `nail-personalization-skin-sampling.test.ts` 中加一条「复制常量与来源文件常量一致」的快照断言，来源常量变更时该测试失败并强制人工复核。

依据：环状证据法在项目内已有先例（局部近景检测的肤色邻环，资料汇编 §1）；ITA° 需在未受病变/污染区域计算的教训见 [S39]；阴影压低 ITA° 与深肤色系统性低判见 [S39][S81]，缓解手段为 quality 门 + 用户自评覆盖 + 页面提示。

### 3.4 hand-profile.ts（手型/甲床分析）

```ts
export function analyzeHandProfile(candidates: readonly NailTextureCandidate[]): HandProfile;
```

0. **手轴旋转归一化（2026-10-20 新增；原公式在斜拍/竖拍下必然失真）**：以有效候选 `angle` 的中位数为主轴角 θ，把各候选中心旋到手轴坐标系后再算跨度与相对宽度。`angle` 全为 null 或有效候选 < 3 时跳过旋转、置 `palmAspect = null` 并出 `hand_profile_axis_unknown` 警告。
1. 过滤无效候选：① `length <= 0 || width <= 0`；② 中心越界（超出图像边界且距离 > 半个长轴）；③ **重复甲面判据（原文档缺失）**——两候选中心距 < 较小半长轴 × 0.6 且长轴夹角 < 25° 判为重复，保留 `score` 较高者，被剔除者计入 `duplicateCandidates`；④ `aspectRatio` 落在 `[0.4, 4.0]` 之外视为异常几何，剔除并警告。
2. 逐候选产 `NailBedMetrics`：`aspectRatio = length/width`，`relativeWidth = width / 有效候选宽度中位数`（有效候选 < 3 时中位数不稳定，仍计算但由第 5 条降级）。
3. `palmAspect = 手轴 x 跨度 / (手轴 y 跨度 + 甲长中位数)`——**近似量，且量纲已修正**：分子与分母各分量统一为「手轴坐标系下的像素距离」，消除原式「跨度 + 甲长」混用不同量纲的问题。掌宽/掌长原始口径依赖手部关键点（**[S30] Gunasekera 2025 与 [S31] IEEE 2024 是两篇不同文献**，不得合并表述），v1 候选不含掌部 landmarks，不可复现、**不假装精确**。
4. 分类常量表 `HAND_SHAPE_THRESHOLDS`：
   - `wide-short`：`medianNailAspect < 1.25 && palmAspect > 0.72`
   - `narrow-long`：`medianNailAspect > 1.55 && palmAspect < 0.62`
   - `slim-tapered`：`thumbRatio > 0.78 && medianNailAspect > 1.40`
   - 其余 `balanced`
   **拇指候选缺失处理（2026-10-20 新增）**：`suggestedFinger` 可能为 `null`（白皮书 §6.1 `NailTextureCandidate.suggestedFinger: number | null`）。无拇指候选或 `thumbRatio` 不可计算时置 `thumbRatio = null`，`slim-tapered` **不得命中**（不得用其它指替代拇指），出 `hand_profile_thumb_unknown` 警告；`palmAspect === null` 时 `wide-short`/`narrow-long` 同样不得命中，结论回落 `balanced`（**不得把"无法判定"当成 `balanced` 的正面证据**，两者仅输出值相同，来源字段须区分）。
5. `completeness = (有效候选数 / 期望候选数) × mask 与 suggestedFinger 加权`（权重常量 `COMPLETENESS_WEIGHTS` 置于文件顶部）。`completeness < 0.6` → 警告 `hand_profile_insufficient_candidates`，推荐置信度封顶 medium。

### 3.5 nail-health.ts（指甲健康启发式，严格限定）

```ts
export function analyzeNailHealthHeuristic(
  image: ImagePixels,
  candidates: readonly NailTextureCandidate[] // 仅使用带 mask 的候选
): NailHealthHeuristic | null;                 // 无 mask 候选 → null
```

- `colorUniformity`：mask 前景 Lab L\* 的稳健离散度（MAD）归一化；
- `highlightRatio`：复用 `src/lib/nail-texture-recognition/extract-mask-texture.ts` 导出的 `isSpecularHighlightPixel()`（L\* 高且低饱和）判据的像素占比——**只读 import，不得修改该文件**（属识别管线，见 §4 禁改清单）；
- `textureStreaking`：沿 `candidate.angle` 方向的梯度均值 / 垂直方向梯度均值（`angle` 为 null 时以垂直方向为主轴，并出 `nail_health_axis_unknown` 警告）；
- `score = round(100 × (w1×colorUniformity + w2×(1−highlightRatio) + w3×(1−textureStreaking)))`；**权重取值（2026-10-20 明确；原只写「文件顶部常量」导致无法黄金测试）**：`NAIL_HEALTH_WEIGHTS = { uniformity: 0.5, highlight: 0.3, streaking: 0.2 }`（和为 1）。该组权重为**预注册假设，无外部效度来源**（资料汇编 §2.5 第 4 条：竞品 0–100 评分无公开算法），**不得对外表述为"健康评分"的准确度量**；
- **硬约束**：输出恒带 `heuristicOnly: true`；present 层文案固定含「启发式观察，不构成医疗或诊断结论」；**不做任何疾病分类**；无 mask 候选时返回 `null`——**当前正式模型未部署期间识别 100% 走 fallback，该通道恒为 null**（见 §6）。

### 3.6 rules.ts（纯规则引擎）

```ts
export interface NailShapeRule { id: string; weight: number; shape: NailShapeAdvice; length: LengthAdvice;
  when: (p: HandProfile, s: UserScenario) => boolean; explain: (p: HandProfile, s: UserScenario) => string; }
export interface ColorRule { id: string; weight: number; colors: ColorAdvice;
  when: (skin: SkinToneAnalysis | null, s: UserScenario) => boolean; explain: (skin: SkinToneAnalysis | null, s: UserScenario) => string; }
export const NAIL_SHAPE_RULES: readonly NailShapeRule[];
export const COLOR_RULES: readonly ColorRule[];
export function recommend(profile: HandProfile, skin: SkinToneAnalysis | null, scenario: UserScenario,
  options?: { backend?: "model" | "fallback"; topK?: number }): Recommendation[];
```

评分与排序（确定性、可黄金测试）：

0. **硬过滤（2026-10-20 新增，先于打分）**：`manualLabor === "heavy"` 或 `nailCondition ∈ {"thin-soft","brittle"}` 时，从甲型候选集**移除**所有 `length === "long"` 组合，并附 `safety-long-length-excluded`（severity=warning）说明。理由：重劳作断甲风险与薄软甲加固需求是安全约束，不能靠权重竞争表达——原设计会让 `shape-heavy-labor-squoval`(w4) 与 `occasion-party-bold-almond`(w2) 同时命中，出现「重体力场景推荐杏仁长甲」的自相矛盾输出。
1. **同组合不重复计分（2026-10-20 修正）**：同一 `shape+length` 组合被多条规则命中时取**最高权重**作为该组合分（不再求和），其余命中规则转为 `explanations` 的 info 条目并注明「已按更优先规则合并」。原设计对 `shape-wide-short-round`(w3) 与 `shape-short-bed-round`(w2) 求和，导致 round/short 分数虚高、排序失真。色系同理：同一 `family` 多命中时取最高权重。
2. 甲型候选分、色系候选分分别按上条聚合得出。
3. **归一化后再组合（2026-10-20 修正）**：甲型分与色系分各自除以该维度**当前实际最大命中权重**归一到 [0,1]，再按 `SHAPE_COLOR_BLEND = { shape: 0.5, color: 0.5 }` 加权求和。原式「甲型分 + 色系分」直接相加，两维度量纲不同（上限不等），排序不可解释且黄金断言不稳。
4. 甲型 Top-3 × 色系 Top-3 按组合分降序组成推荐，去重，截断 topK（默认 3）；`id` 按 §3.1 的确定性规则派生。
5. `explanations` = 计入分数的规则文案按权重降序（severity：安全/覆盖类标 warning，其余 info）；`ruleHits` **只记录实际计入分数的规则 id**（被合并或压制的不进，便于测试区分）。
6. 置信度：`backend === "fallback"` 或存在低置信候选 → `requiresManualConfirmation = true` 且封顶 medium；`completeness < 0.6` 或 `skin === null` 再降一档。
7. 用户自评底调优先：调用方组 `SkinToneAnalysis` 时以 `selfReportedUndertone` 覆盖 `undertone` 并标记来源；规则无感，文案区分「测得/你自评」。

**规则表注（2026-10-20 修订）**：

1. `occasion` 为必填；`style` / `manualLabor` / `lengthPreference` / `nailCondition` 为可选，**未填一律按 unknown 处理**。条件中**禁止**对可选字段直接用 `!==` 取反（`undefined !== "long"` 恒为 true，会把"未填"当成"非长"）；需要"非某值"语义时必须写成 `x !== undefined && x !== "long"` 或显式 `isKnown(x)` 判定。
2. 每条规则 `when` 首判其依赖的分析对象非 null（`skin !== null`、手型已判定等），null 时该规则自动失效，不抛错。
3. `season` 字段**仅作展示标签，不参与任何规则命中**（资料汇编 §2.5 第 1 条：四季色彩无同行评审效度验证）。
4. 低 ITA°（dark）档位规则必须叠加采样质量门，见颜色规则 `color-ita-deep-jewel`（资料汇编 §2.5 第 3 条）。
5. **肤色类规则总闸（2026-10-20 第二轮新增）**：7 条 `color-undertone-*` / `color-ita-*` 规则的 `when` 首判 `chromaUsable(skin)`，即 `skin !== null && skin.itaReliable === true`。`itaReliable === false`（低彩度或近分档边界）时这些规则**整体弃权**，`ruleHits` 不含任何肤色规则；场合/风格/长度/甲面状况规则不受影响，保证用户始终有推荐、且不会拿到一个看似精确的错档色系。

**完整规则表**（来源编号见资料汇编 §3；presetNames 全部引用 `src/lib/utils.ts` 既有 20 色，测试强制校验存在性）：

甲型规则（NAIL_SHAPE_RULES，11 条；2026-10-20 修订）：

| id | 权重 | 条件 | 建议 | 解释要点 |
| --- | --- | --- | --- | --- |
| shape-heavy-labor-squoval | 4 | manualLabor=heavy | squoval/short | 方圆形短甲边角厚不易劈裂，洗漱日常耐用（安全类规则，触发 §3.6 第 0 条硬过滤） |
| occasion-work-squoval | 3 | occasion=work | squoval/short | 职场通勤低干扰，短方圆稳重不突兀 |
| style-low-maintenance-round | 3 | style=low-maintenance | round/short | 圆形长出最自然、免频繁修型 |
| shape-wide-short-round | 3 | shape=wide-short && lengthPreference≠long（须先判 known，见规则表注 1） | round/short | 甲床偏短宽，圆形收敛两侧显修长 |
| shape-narrow-long-oval | 3 | shape=narrow-long && occasion≠party | oval/medium | 甲床偏长窄，椭圆顺应自然比例 |
| shape-slim-tapered-almond | 2 | shape=slim-tapered（thumbRatio=null 时不可命中） | almond/medium | 拇指相对窄+甲面长，杏仁延伸优雅线条 |
| shape-balanced-squoval | 2 | shape=balanced | squoval/medium | 比例均衡，方圆形百搭耐用 |
| occasion-wedding-oval | 2 | occasion=wedding && lengthPreference≠short（须先判 known） | oval/medium | 婚礼中长椭圆/杏仁衬纱与戒指 |
| occasion-party-bold-almond | 2 | occasion=party && style=bold | almond/long | 派对+夸张风格，杏仁长甲有存在感；**受第 0 条硬过滤约束**（重劳作/薄软甲时该组合被移除） |
| shape-short-bed-round | 2 | medianNailAspect<1.2 && shape≠wide-short | round/short | 甲床偏短（含啃咬甲），圆形不需长度基底；**与 shape-wide-short-round 互斥**，避免同一 round/short 组合重复计分 |
| nail-condition-thin-soft | 3 | nailCondition∈{thin-soft,brittle} | squoval/short | 甲面薄软或易断，先做建构胶/水晶甲加固再谈款式与长度（资料汇编 §3.4）；同时触发第 0 条硬过滤 |

颜色规则（COLOR_RULES，15 条；2026-10-20 修订）：

| id | 权重 | 条件 | 色系（presetNames） | 季型 |
| --- | --- | --- | --- | --- |
| occasion-work-nude | 4 | occasion=work | 职场裸色：裸粉色/裸色/奶茶色 | — |
| occasion-wedding-elegant | 4 | occasion=wedding | 婚礼优雅色：裸粉色/纯白色/银色 | — |
| color-undertone-warm-rich | 3 | undertone=warm && itaBand∈{brown,tan} | 暖调浓郁色：酒红色/焦糖色/樱桃红 | autumn |
| color-undertone-cool-soft | 3 | undertone=cool | 冷调柔雾色：雾霾蓝/薰衣草紫/豆沙红 | summer |
| color-undertone-warm-bright | 3 | undertone=warm && itaBand∈{very-light,light} | 暖调明亮色：珊瑚粉/橘色/金色（**原列「抹茶绿」与资料汇编 §3.2 暖调配色不符，已替换**） | spring |
| color-undertone-neutral-balanced | 3 | undertone=neutral | 中性平衡色：酒红色/豆沙红/裸粉色（**新增**：原规则表缺 neutral 专属规则，中性底调用户只能走场合规则） | — |
| color-ita-deep-jewel | 3 | itaBand=dark **&& skinQuality≥0.5**（质量门，见备注） | 宝石亮色：玫红色/深蓝色/金色 | winter |
| occasion-party-bold | 3 | occasion=party && style=bold | 派对闪耀色：亮片银/金色/黑色 | — |
| color-undertone-olive-earth | 2 | undertone=olive | 大地浓郁色：焦糖色/抹茶绿/奶茶色 | autumn |
| color-ita-fair-soft | 2 | itaBand∈{very-light,light} && undertone∉{warm} | 柔粉淡紫：裸粉色/豆沙红/薰衣草紫 | summer |
| occasion-date-romantic | 2 | occasion=date | 约会浪漫色：酒红色/豆沙红/樱桃红 | — |
| occasion-vacation-bright | 2 | occasion=vacation | 度假明亮色：珊瑚粉/橘色/抹茶绿 | — |
| occasion-daily-safe | 1 | occasion=daily | 日常安全色：裸粉色/豆沙红/珊瑚粉 | — |
| length-optical-light | 1 | lengthPreference=short ‖ medianNailAspect<1.2 | 浅裸拉长色：裸粉色/裸色/纯白色 | — |
| nail-condition-safe-base | 1 | nailCondition∈{thin-soft,brittle} | 加固友好色：裸粉色/奶茶色/裸色（浅色便于观察甲面变化，配合加固建议） | — |

**`color-ita-deep-jewel` 质量门备注（2026-10-20 新增）**：[S39][S81] 指出阴影/差光照会把图像系统性压到低 ITA°，深色图像无论真实肤色均被判为 dark。因此该规则在 `skinQuality < 0.5` 时**不命中**，改出 `skin_tone_low_quality_color_fallback` 提示并回落场合规则；**不得因"看起来是深肤色"就绕过质量门**。

规则完备性说明（2026-10-20 修订）：

1. `skin === null` 时全部肤色规则自动失效（`when` 首判 `skin !== null`），推荐降级为纯场景/风格/手型驱动并出 `skin_tone_unavailable_color_fallback` 提示。
2. 底调四值（warm/cool/neutral/olive）**必须各有至少一条专属规则**，缺任一即视为规则表不完备（测试断言）。
3. 每条规则至少一个命中 fixture（测试强制，防静默漂移），且**新增规则必须同步新增 fixture 与黄金断言**，不允许出现"有规则无测试"。
4. 规则 id 唯一、权重与条件变更后必须同步黄金测试；`presetNames` 全部存在于 `PRESET_COLORS`（测试强制校验）。

### 3.7 present.ts（中文解释文案层）

复刻 `src/components/nail-art-picker-quality.ts` 模式：

```ts
export function summarizeSkinTone(skin: SkinToneAnalysis | null): PresentationSummary | null;
export function summarizeHandProfile(profile: HandProfile): PresentationSummary;
export function summarizeNailHealth(health: NailHealthHeuristic | null): PresentationSummary | null;
export function presentRecommendation(rec: Recommendation): PresentationSummary;
export function auxiliaryAnalysisNotice(backend: "model" | "fallback", candidateCount: number): string | null;
```

- `PresentationSummary = { severity: "ok" | "review" | "info"; title: string; messages: string[]; stats?: ... }`；
- warning code → 中文文案映射表 + severity 分级（琥珀/翠绿徽章渲染由组件负责）；
- **提示层级与去重（2026-10-20 新增；原文档三处提示无去重规则）**：warning code 是唯一去重键。同一 code 会同时出现在 `HandProfile.warnings`、`PersonalizationResult.notices`、`RecommendationExplanation` 三个层级；呈现优先级为 `notices` > `explanation` > `profile.warnings`，**同一 code 只保留最高层级一处**。`present.ts` 提供 `dedupeWarnings(codes: readonly string[]): string[]` 纯函数按此收敛，测试断言同一 code 在结果中只出现一次。
- `auxiliaryAnalysisNotice` 与既有 `auxiliaryDetectionNotice` 同构：fallback 时返回「当前为辅助定位结果，甲面边界未经正式模型确认；分析结论仅供参考，请结合实物效果判断。」
- 指甲健康文案固定含「启发式观察，不构成医疗或诊断结论」；肤色文案注明「非受控拍摄，ITA° 仅供色号筛选参考」，**且不得出现 Monk 等级或季型的"科学测定"表述**（资料汇编 §2.5 第 1、2 条）。

### 3.8 index.ts 与 bridge.ts

```ts
// index.ts：纯编排，Node 可全量测试
export function analyzeNailPersonalization(input: PersonalizationInput): PersonalizationResult;

// bridge.ts：出站参数桥接（照 src/lib/gallery-bridge.ts 先例）
export function buildAnalysisBridgeParams(rec: Recommendation): { preset: string; shape: string };
export function parseAnalysisBridgeParams(params: { preset?: string | null; shape?: string | null }):
  | { ok: true; preset: string; shape: NailShapeAdvice } | { ok: false };
```

`preset` 必须是 PRESET_COLORS 中的 name、`shape` 白名单校验；非法一律拒绝降级为普通跳转（不抛错）。落地形态：`/editor?preset=<色名>`，编辑器以 `useSearchParams` 消费（与 `?gallery=` 同构），把推荐色预涂到当前手指；甲型/长度建议作为 AR 页可选预填列为后续 stretch，不进 v1 验收。

**参数优先级（2026-10-20 明确）**：`?preset=` 与既有 `?gallery=` 同时传入时，**`gallery` 优先**（沿用既有行为，避免改动现有灵感链路），`preset` 被忽略并在 notices 记 `preset_overridden_by_gallery`；两者都非法时降级为普通跳转。`shape` 在 v1 写入但编辑器**不消费**（不渲染、不报错），避免协议字段与实际行为不符。

---

## 4. 集成点清单

| 集成点 | 文件 | 改动性质 |
| --- | --- | --- |
| 识别直连 | `src/lib/nail-texture-recognition/index.ts`、`input-scaling.ts`（`remapNailTextureCandidatesToOriginal`） | 只读调用，**禁改** |
| 高光判据 | `src/lib/nail-texture-recognition/extract-mask-texture.ts`（`isSpecularHighlightPixel`） | 只读 import，**禁改**（2026-10-20 补登记：§3.5 已引用但原表漏项） |
| 上传校验 | `src/lib/image-upload-validation.ts`（10MB / 320–4096px / MIME 三选一） | 只读复用 |
| 导航入口 | `src/app/page.tsx`（首页功能入口，现 4 项）、`src/components/Header.tsx`（导航，现 4 项） | 小改，**新增 `/nail-analysis` 条目**（2026-10-20 补登记：原表漏项，C 端功能无入口即不可达） |
| 新页面 | `src/app/nail-analysis/page.tsx`（AppShell + 状态机 idle→analyzing→result） | 新建 |
| 新组件 | `src/components/NailAnalysisForm.tsx`（问卷）、`src/components/NailAnalysisResult.tsx`（推荐卡+琥珀提示） | 新建 |
| 出站消费 | `src/app/editor/page.tsx` 增加 `?preset=` 消费（约 20 行，照 `?gallery=` 模式） | 小改 |
| 隐私页 | `src/app/privacy/page.tsx` 功能枚举增加「个性化分析推荐 · 默认本地」一行 | 小改 |
| 禁改清单 | 识别管线全部、`nail-hand-geometry-detection.ts`、`nail-partial-closeup-detection.ts`、`NailArtPicker.tsx`、`ar-tryon/*`、`model/*`、`public/models/*` | **零改动**（与纹理模型 Goal 隔离） |

新页面检测编排按 `/device-benchmark` 先例自持一份精简编排（worker 识别 → remap → fallback 链），不抽取共享函数、不改 NailArtPicker，并在注释注明重复原因。

**编排重复点的同步责任（2026-10-20 新增）**：至此仓库将存在三份 fallback 编排（`NailArtPicker.tsx`、`/device-benchmark`、`/nail-analysis`）。**琥珀辅助定位提示是发布拦截项**，三处文案与判定条件必须一致，因此：①新页面的 fallback 判定与提示文案**不得自行实现**，须与既有 `auxiliaryDetectionNotice()`（`src/components/nail-art-picker-quality.ts`）的输出保持同源；②在页面文件头部注释中登记「本编排为 NailArtPicker 的精简副本，同步责任人=本功能维护者」；③`nail-personalization.test.ts` 增加一条"琥珀文案与 `auxiliaryDetectionNotice` 同构"的断言，防止后续三处漂移。

---

## 5. 隐私合规

- 全部计算在浏览器本地：识别（Worker/主线程）、肤色采样（canvas getImageData）、规则引擎（纯函数）；**不新增任何上传通道**；
- **「用户改进计划」与本功能的边界（2026-10-20 明确）**：本功能产出的是**人体特征推测结果**（肤色、甲床比例、健康启发式），敏感度高于一般偏好设置。因此预注册：**即使「用户改进计划」开关处于开启状态，本功能的分析结果（含图片、采样像素、肤色/手型/健康结论）也不进入任何上传通道**；/privacy 新增文案只写「个性化分析推荐 · 默认本地处理，分析结果不外发」，**不得写成绝对化的「永不上传」承诺**（与白皮书 §10「改进计划模式」口径保持一致，避免法律审核冲突）。
- ImageBitmap / canvas / objectURL 在取消与卸载时释放（照白皮书 §10 资源释放清单）；
- 隐私判断依据：矩阵中仅 Cutie Nails 强调照片仅本地 [S15]——本地处理既是项目原则也是竞品空位，UI 应明示。

---

## 6. PRODUCT HOLD 边界（必须如实呈现）

0. **当前可达性声明（2026-10-20 新增，验收前必读）**：正式纹理模型当前处于 PRODUCT HOLD、manifest `not-deployed`，识别**实际 100% 走 fallback，无像素级 mask**。因此在当前事实下：①`nailHealth` **恒为 `null`**（不是"实现了但失败"，而是依赖的 mask 通道尚不存在）；②肤色采样只走椭圆几何路径；③手型与健康结论都建立在未经确认的候选几何上。页面必须**常显**琥珀声明，且**本功能的任何输出都不得计入正式识别成功率、模型指标或 Beta 直接可用率**。文档与验收记录不得把上述降级写成"功能已实现"。
1. `backend === "fallback"` 或任一候选 `confidence === "low"`：页面级琥珀声明 + 每条推荐 `requiresManualConfirmation = true`；文案统一「辅助分析结果，请结合实物效果判断」，**禁止「自动分析完成/精准推荐」话术**；
2. 无 mask 候选（mediapipe/局部近景路径）：`nailHealth = null`，UI 隐藏健康评分而非展示猜测值，警告 `nail_health_requires_mask`；
3. 肤色采样质量不足：`skinTone = null`，颜色推荐降级为场合/风格规则，警告 `skin_sampling_low_quality`；低 ITA° 档位额外受 `color-ita-deep-jewel` 质量门约束（§3.6）；
4. **0 候选与识别失败路径（2026-10-20 新增）**：识别返回 0 候选、Worker 超时或抛错时，页面**不得**基于空候选生成任何推荐（空推荐会伪装成"没有适合你的款式"）。必须：①置状态为 `error`/`no-candidates` 并显示「未能定位到甲面，请重新拍摄（五指清晰、光照均匀）」；②提供与白皮书 §3「传统算法降级」行一致的「手工添加」入口；③`notices` 记 `no_candidates_no_recommendation`，**不计为一次成功分析**。
5. 以上全部复用既有 warning code 模式（参考 `nail-art-picker-quality.ts`），不发明新状态机。

---

## 7. 测试计划

测试文件（`tests/*.test.ts`，node --test + node:assert/strict，从 `../src/lib/nail-personalization/...` 导入；合成 fixture 全部内存构造，不提交二进制）：

| 测试文件 | 覆盖 | 关键用例 |
| --- | --- | --- |
| nail-personalization-color-science.test.ts | Lab/ITA°/Monk/底调/ΔE | 已知 Lab 的 sRGB fixture 断言 ITA° 容差 ±1°；**分档边界开闭逐值断言（55→light、41→intermediate、28→tan、10→brown、−30→dark）**；Monk 分档单调；**底调四值与优先级边界（橄榄优先于暖：`a*=3,b*=20` → olive）**；非法输入 null |
| nail-personalization-color-science-fairness.test.ts | **肤色公平性（2026-10-20 新增）** | **ITA° 六档 × 底调四类合成矩阵**逐一断言分档正确；**同一"皮肤"在暖光/冷光/阴影三套光照下的 ITA° 漂移**断言不跨档或触发质量门；**深肤色（dark）在阴影下不得误触发 `color-ita-deep-jewel`**（质量门生效） |
| nail-personalization-skin-sampling.test.ts | 肤色环采样 | 已知肤色环+异色甲面+背景噪点合成图 → 聚合 Lab 复现已知值（中位数抗噪）；mask/椭圆两路径；候选贴边；皮肤像素全滤除 → quality=0；**甲面自污染排除（采样点落在甲面/邻甲内被剔除）**；**绝对下限 `MIN_SKIN_SAMPLES` 生效**；**复制常量与 `nail-partial-closeup-detection.ts` 一致的快照断言**（防规则漂移） |
| nail-personalization-hand-profile.test.ts | 手型分类 | 短宽→wide-short、长窄→narrow-long、拇指宽→slim-tapered、混合→balanced；候选<3 → completeness 低+警告；零尺寸/越界/异常 aspectRatio 候选被过滤；**重复甲面判据生效**；**手斜置（旋转 30°/90°）下分类结果与正视一致**（旋转归一化）；**`suggestedFinger=null` 时 slim-tapered 不命中且出警告**；**`palmAspect=null` 时回落 balanced 但来源标记为"不可判定"** |
| nail-personalization-nail-health.test.ts | 健康启发式 | 均匀色 mask→高均匀低条纹；条纹 mask→streaking 升高；高光 mask→highlightRatio；无 mask→null；`angle=null` 时的主轴回退；**断言恒含 heuristicOnly 且文案无医疗措辞**；**断言权重常量取值 0.5/0.3/0.2** |
| nail-personalization-rules.test.ts | 规则引擎黄金样 | 固定 (HandProfile, Skin, Scenario)→精确 top-K 推荐 id 与 ruleHits、explanation 逐字断言；fallback→requiresManualConfirmation；skin=null 降级路径；**可选字段未填（undefined）不得被当作否定值**；**同 `shape+length` 组合多命中时取最高权重不求和**；**归一化后的组合分排序稳定**；**硬过滤：heavy labor / thin-soft 时无 long 组合**；**neutral 底调有专属规则命中**；规则 id 唯一；presetNames 全部存在于 PRESET_COLORS |
| nail-personalization-rules-coverage.test.ts | **规则覆盖 meta-test（2026-10-20 新增）** | 遍历 `NAIL_SHAPE_RULES` 与 `COLOR_RULES`，**自动断言每条规则至少有一个命中 fixture**、id 唯一、权重>0、`explain()` 非空；断言底调四值各有专属规则。新增规则未加 fixture 时该测试失败，杜绝"有规则无测试" |
| nail-personalization-present.test.ts | 文案层 | severity 分级；**`dedupeWarnings` 同一 code 只保留最高层级一处**；琥珀 notice；health/skin 为 null 时的隐藏语义；**文案不含「科学测定季型」「Monk 等级」等越界表述** |
| nail-personalization-bridge.test.ts | 参数桥接 | 合法往返；非法 preset/shape 拒绝（照 tests/gallery-bridge.test.ts 模式）；**`?preset=` 与 `?gallery=` 同时传入时的优先级（见 §3.8）** |
| nail-personalization.test.ts | 编排入口 | 端到端合成输入→PersonalizationResult 全字段断言；fallback+低质量采样组合降级链；**0 候选时不产出任何推荐且 notices 含 `no_candidates_no_recommendation`**；**琥珀文案与 `auxiliaryDetectionNotice` 同构**；**传入非原图像素（`pixelSource` 缺失）时类型层拦截** |
| nail-personalization-performance.test.ts | **性能与内存（2026-10-20 新增）** | 4096×4096 合成原图上断言**采样循环 <50ms**（不含 `getImageData` 与解码，两者单独计时并登记）；断言采样阶段不额外分配整图副本；阈值失败即失败，不得放宽 |

验证命令（Windows 必须 `npm.cmd`，**串行**）：`npm.cmd test` → `npm.cmd run typecheck` → `npm.cmd run typecheck:tests` → `npm.cmd run lint` →（页面落地轮）`npm.cmd run build`。新测试文件被 `tests/*.test.ts` 通配自动纳入。

**Windows 环境前提（2026-10-20 补记）**：`npm.cmd test` 会启动裸 `python` 子进程，运行前必须把 `C:\Users\YaoYinyu\AppData\Local\Programs\Python\Python313` 显式置于当前进程 `PATH` **首位**（本机默认 Python 缺 Pillow/Shapely 会造成与本功能无关的假性失败）；该失败属环境失败，修正环境后串行重跑，**不得据此放宽断言或跳过检查**。

---

## 8. 里程碑与验收标准（预注册）

| # | 里程碑 | 产物 | 完成标准 | 停止/回滚条件 |
| --- | --- | --- | --- | --- |
| M1 | color-science.ts + 测试 | `color-science.ts`、色彩科学测试、公平性测试 | 上述色彩科学用例全过（含 ITA 边界开闭与底调优先级）；公平性矩阵全过；串行 test/typecheck/typecheck:tests/lint 全绿 | 若非受控光照下 ITA° 漂移无法被质量门约束（合成矩阵跨档误判 >10%），停止并回到采样方案设计，不得靠放宽容差通过 |
| M2 | hand-profile.ts + 测试 | `hand-profile.ts`、手型测试 | 四类手型合成样本分类正确（含旋转 30°/90° 一致）；候选不足/无效输入/重复甲面路径有警告且 completeness 正确；`suggestedFinger=null` 与 `palmAspect=null` 路径通过 | 斜置样本分类一致性 <90% 即说明旋转归一化不足，停止并重做手轴估计，不得只对正视样本调优 |
| M3 | skin-sampling.ts + 测试 | `skin-sampling.ts`、采样测试 | 合成环图复现已知肤色 Lab（容差内）；两路径/贴边/全滤除/自污染排除用例通过；完成预注册假设标定（见下方补充条款） | 合成图都无法稳定复现已知 Lab 时，不得进入真实图验证，停止并修采样几何 |
| M4 | nail-health.ts + 测试 | `nail-health.ts`、健康测试 | 均匀/条纹/高光 fixture 指标方向正确**并断言具体区间**（非仅方向）；无 mask→null；heuristicOnly 恒真且无医疗措辞（断言）；权重常量取值断言 | 当前无 mask 通道（§6 第 0 条），该模块**只能通过合成 mask 验证**，不得在真实 fallback 图上声称已验证 |
| M5 | rules.ts + present.ts + 测试 | `rules.ts`、`present.ts`、规则测试、覆盖率 meta-test、文案测试 | 黄金样例逐字通过；覆盖率 meta-test 100%、id 唯一、presetNames 有效；硬过滤与「同组合取最高权重」生效；fallback→requiresManualConfirmation；skin=null 降级路径 | 新增规则未同步 fixture 导致 meta-test 失败即为阻断项，不得临时关闭 meta-test |
| M6 | 页面与桥接 | `src/app/nail-analysis/page.tsx`、`NailAnalysisForm.tsx`、`NailAnalysisResult.tsx`、`bridge.ts`、`editor` 小改、首页与 Header 导航入口、`/privacy` 一行 | /nail-analysis 本地图走通「识别→分析→问卷→推荐」；**fallback 琥珀声明必现（当前 100% fallback）**；0 候选路径正确；/editor?preset= 预涂生效且优先级符合 §3.8；npm.cmd run build 通过 | 琥珀声明在任一路径缺失即视为发布拦截项，不得上线 |
| M7 | 文档同步 | 白皮书 §3 行 + §4.x 小节、README、当日 dev-log | 按**落地当时的白皮书头部版本顺延一位**并与 dev-log 同一次编辑；README 功能概览/隐私小节同步；全量串行验证通过 | 版本标记与白皮书头部不同步即视为未完成 |

**预注册假设的标定要求（2026-10-20 新增）**：以下数值均为**预注册假设而非标定值**，M1–M3 必须给出标定方法与来源，禁止直接沿用：`ITA_BAND_BOUNDS`、`UNDERTONE_*` 常量、`MONK_ITA_BOUNDS`、`MIN_SKIN_SAMPLES=120`、`quality=0.35`、`HAND_SHAPE_THRESHOLDS`、`NAIL_HEALTH_WEIGHTS`、`SHAPE_COLOR_BLEND`。标定只能使用**与任何模型训练/评估来源隔离的合成或自有新样本**；**禁止**用既有验证真值、已消费 holdout 或受保护数据集做本功能阈值标定。标定后必须同步更新黄金测试与本文档常量说明。

**落地状态（2026-10-20 实现轮）**：M1–M6 已实现并通过工程门，M7 文档同步已随本轮完成；真实照片与真机验收（M6 的用户侧验收部分）仍未完成。

| 里程碑 | 落地结果 |
| --- | --- |
| M1 | ✅ `color-science.ts` + 色彩科学与公平性测试（13 项）。ITA 分档边界开闭、底调优先级（橄榄优先）、Monk ITA° 映射均已实现并锁定 |
| M2 | ✅ `hand-profile.ts` + 测试（10 项）。手轴旋转归一化（斜拍 30°/90° 一致）、重复甲面判据、`suggestedFinger`/`palmAspect` 为 null 的处理均已实现 |
| M3 | ✅ `skin-sampling.ts` + 测试（9 项）。甲面自污染排除、双条件质量门、复制常量来源同步断言均已实现 |
| M4 | ✅ `nail-health.ts` + 测试（8 项）。权重 0.5/0.3/0.2、`isSpecularHighlightPixel()` 复用、无 mask→null、恒 `heuristicOnly` |
| M5 | ✅ `rules.ts` + `present.ts` + `index.ts` + 桥接与覆盖率 meta-test（规则 13 项、覆盖率 5 项、文案 8 项、桥接 6 项、编排 5 项、性能 2 项） |
| M6 | ✅ `/nail-analysis` 页面、问卷/结果组件、`/editor?preset=` 消费（gallery 优先）、首页与 Header 入口、`/privacy` 新增一行、生产构建通过（`/nail-analysis` 静态预渲染） |
| M7 | ✅ 白皮书 §3 状态行 + §4.6 小节、v1.2.133→v1.2.134、README 同步、当日 dev-log 记录 |

**技术路线调整记录（实现轮）**：

1. **`palmAspect` 公式方向**：原设计写「x 跨度 /(y 跨度 + 甲长)」。实现时先做手轴旋转归一化（长轴对齐 +x），此时 x 跨度为**沿指方向**、y 跨度为**跨指方向**，与原式的坐标含义相反；若照抄会把「宽手」判成「窄手」。实现改为 `跨指跨度 /(沿指跨度 + 甲长中位数)`，与 `HAND_SHAPE_THRESHOLDS` 的宽窄口径一致（wide-short 取大值、narrow-long 取小值）。理由：阈值口径不变、几何量在旋转后语义互换，必须同步修正，否则四类手型整体反相。
2. **`textureStreaking` 方向**：原设计写「沿甲长轴梯度 / 垂直轴梯度」，但纵向条纹的梯度本就在横断面，照抄会与「条纹升高」的验收标准自相矛盾。实现改为 `clamp01((垂直轴梯度均值 / 沿轴梯度均值 − 1) / 2)`，只改指标方向，不改阈值体系与权重。
3. **底调橄榄条件**：设计 §3.2 同时写了「4 ≤ b\* ≤ 14」与「a\*>2 且 b\*>14 判 olive」，两者冲突。按「橄榄优先于暖」的意图实现为 `a*>2 && b*≥4`（不设 b\* 上界），并同步修正设计文档。
4. **`isContaminated` 邻甲安全距离取半短轴**：原写「候选半轴 ×1.0」，若取半长轴会把最内圈环采样点（1.15× 半短轴）大量误判为污染，导致单候选采样数掉到绝对下限以下。实现取半短轴，环点全部落在安全距离之外。
5. **`approximateMonkGrade` 采用 ITA° 分档映射**（非 L\* 线性近似），与资料汇编 §8 第 2 条指出的 [S38] 口径一致，并在注释中声明仅供色号筛选沟通。
6. **`auxiliaryAnalysisNotice` 的呈现方式**：`notices` 为 warning code 列表，新增 `auxiliary_analysis_notice` code 与文案映射，避免把长文案直接塞进 code 列表；页面在 fallback 时必现该声明。

**第二轮修订（2026-10-20，跨光照一致性实证后）**：用户质疑「不预处理如何保证一致」。用 `color-science.ts` 对 4 个合成肤色 × 亮度 0.5–1.0 × 三种光源共 72 组定量探针，证实色系建议确实会随光照变化，并发现一处真实缺陷：`|b*|` 接近 0 时 ITA° 饱和到 ±90、分档由 b\* 符号决定（`b*=−0.25`→dark 与 `b*=+0.25`→very-light），受害人群是 b\* 天然接近 0 的浅色/中性皮肤，与 [S38][S40] 已记录的肤色标度偏见同向。据此落地：新增 `classifyItaBandStable()` 与 `ITA_UNSTABLE_B_ABS`/`ITA_BOUNDARY_MARGIN` 常量、`SkinToneAnalysis.itaReliable`/`itaUncertainty` 字段、7 条肤色规则的 `chromaUsable` 总闸、`ita_band_unreliable_low_chroma`/`ita_band_unreliable_near_boundary` 两个 warning code 与文案；同时修正了首轮 fairness 测试中「阴影下 ITA° 单调下降」的过弱断言（该断言只对特定 fixture 成立，会掩盖上述缺陷），改为声明前置条件并新增 b\*→0 不连续性与边界余量回归。**明确不做**：亮度/曝光归一化（摧毁被测信号）与整图白平衡（皮肤主导画面无可靠参考白）。

---

## 9. 白皮书登记草稿（功能落地轮使用）

**§3 状态表新增行**：

> **状态口径（2026-10-20 修正）**：下列草稿中的「待验证」**不可直接照抄**。须按白皮书 §1.1 状态定义据实登记：未开工=**未完成**；库层完成但页面未落地=**进行中**；页面已落地且有本地图走通但缺真机/真实数据验收=**待验证**。草稿只提供「当前结论」列的文案，状态列按落地时实际填写。

```md
| 个性化美甲分析推荐 | `/nail-analysis` | <按 §1.1 据实填写：未完成 / 进行中 / 待验证> | 浏览器本地分析手型/甲床比例、肤色（ITA°与底调）与指甲健康启发式，结合场景问卷由规则引擎推荐甲型、色系与长度并附中文解释；全部本地计算不上传。候选未经正式模型确认时以琥珀辅助提示标注，不算自动分析成功 |
```

**§4.6 小节**（照 §4.4 /ai-generate 先例，插在 §4.5 之后）：

```md
### 4.6 `/nail-analysis` 个性化分析推荐

状态：<按 §1.1 据实填写>（纯规则启发式，不引入新模型训练）。**当前正式模型未部署期间，本页识别 100% 走辅助定位、无像素级 mask，指甲健康通道不可用（隐藏而非降级展示）**。

使用方式：
1. 上传或拍摄一张五指清晰的手背照片（复用同一上传校验：JPG/PNG/WebP、≤10MB、320–4096px）；
2. 系统本地完成甲面候选识别（正式模型不可用时走 MediaPipe/局部近景辅助定位并明确提示人工确认）；
3. 填写场景问卷（场合/风格/劳作强度/长度偏好，可自评底调覆盖测量值）；
4. 查看分析：手型与甲床比例、肤色 ITA°与底调（附采样质量）、指甲健康启发式（附非医疗声明）；
5. 查看推荐卡片（甲型+长度+色系+「为什么适合」+置信度）；
6. 点击推荐色跳转 /editor?preset=<色名> 预涂试色。

数据边界：照片、候选与采样全部浏览器本地处理；不新增上传通道；ImageBitmap/canvas/objectURL 在取消与卸载时释放。

核心组件接口：

```ts
function analyzeNailPersonalization(input: PersonalizationInput): PersonalizationResult
```

前置条件：无新增环境变量；识别库直连方式同 /device-benchmark。琥珀辅助定位边界同纹理识别：fallback 候选未经人工确认，不得表述为自动分析成功。

已知限制：手型为甲面派生近似比例（候选不含掌部 landmarks）；肤色 ITA° 在非受控光照下仅供色号筛选；指甲健康为启发式观察，不构成医疗诊断；规则表为 TS 常量，调整须同步黄金测试。

关联文档：docs/nail-personalization-research.md（资料汇编）、docs/nail-personalization-design.md（设计）。
```

版本与日志（2026-10-20 改为动态口径）：落地轮按**当时的白皮书头部版本顺延一位**（原写死的「v1.2.133 → v1.2.134」已失效——版本号会随其他实质变更漂移，登记时必须现场读取白皮书头部），当日 dev-log 以同一「白皮书 v1.2.x」标记与白皮书头部在**同一次编辑**中同步；若同轮更新 /privacy 与 README，按 AGENTS.md 在提交前一并同步（无用户明确要求不提交）。

**不顺延版本的情形**：仅修订本文档或资料汇编（不涉及代码、接口、状态、数据或模型契约）时，**不改白皮书正文、不顺延版本号、不产生版本标记**，只在当日 dev-log 记录修订内容与「无接口/状态变化」结论。

---

## 10. 风险与边界

1. **纯规则推荐的定位**：输出是「可解释的启发式建议」而非个性化保证；卡片必带解释与置信度；学术指标（90%/95%/86.5%）属其受控实验条件，不可迁移为本产品话术。
2. **肤色测量的光照/设备偏差（含公平性）**：ITA° 源于受控条件 [S38][S80]；阴影/差光照系统性压低 ITA° [S39]，深色图像无论真实肤色均被判为低档，构成对深肤色用户的系统性误判 [S81]；Fitzpatrick/Monk 存在偏见文献 [S33][S38][S40]。缓解：中位数聚合、双条件 quality 门（`quality<0.35` 或 `sampleCount<MIN_SKIN_SAMPLES` 即隐藏）、用户自评底调覆盖、`color-ita-deep-jewel` 额外质量门、Monk 仅作色号筛选沟通且**不输出 Fitzpatrick**、页面明示「非受控拍摄仅供参考」。
3. **指甲健康启发式的医疗边界**：只做均匀度/高光/条纹三类观察，不做疾病分类 [S32][S34][S37]；固定非医疗声明，测试断言文案。
4. **手型近似的局限**：v1 仅用候选派生比例；掌宽/掌长口径不可复现（**[S30] Gunasekera 2025 与 [S31] IEEE 2024 为两篇不同文献**）；landmark 透传列为后续可选，不触碰现有管线。
5. **PRODUCT HOLD 隔离**：不训练、不改模型、不改识别链路；辅助定位输入未经人工确认时如实标注。
6. **规则表漂移**：规则为 TS 常量 + 黄金测试；运营调整必须同步测试，以测试锁防静默漂移。
7. **资料时效**：市场数据与竞品结论带口径年份；落地轮若与资料冲突，以可复现当前事实为准（白皮书 §1.2 优先级原则同样适用于设计文档维护）。资料汇编 §2.5 登记的反面证据优先于任何正面营销材料。
8. **Monk 与季型的表述越界（2026-10-20 新增）**：Monk 只能用 ITA° 映射且须标注「仅供色号筛选沟通」；若实现改用 L\* 线性近似必须在注释声明无来源支持。四季色彩**只作展示标签**，任何「科学测定季型」的文案都属越界。
9. **fallback 编排重复三处（2026-10-20 新增）**：`NailArtPicker` / `/device-benchmark` / `/nail-analysis` 各持一份编排，琥珀提示文案是发布拦截项，三处漂移会造成合规表述不一致。缓解见 §4「编排重复点的同步责任」。
10. **当前可达性风险（2026-10-20 新增）**：正式模型未部署期间本功能 100% 走 fallback，`nailHealth` 恒 null、0 候选概率上升。风险不在代码而在**验收记录被误写成"功能已实现"**——§6 第 0 条为强制口径，任何里程碑报告都必须复述该边界。

---

## 11. 关联文档

- `docs/nail-personalization-research.md`：竞品矩阵、学术注释、领域知识库（规则来源）、技术方法、市场数据、公开数据集、来源 URL 全清单；**§2.5 争议/失效/不可迁移证据**与**§9 检索方法与维护说明**是本文档的硬约束来源。
- `docs/technical-whitepaper.md`：§2（本地处理原则）、§3（状态总表）、§4.4（页面登记先例）、§6（识别接口）、§10（隐私）、§12（登记模板）。
- `docs/nail-texture-current-goal.md`：纹理模型 Goal——本功能与其零交集（不训练、不改模型），但推荐功能消费其识别输出，须遵守 §6 的 HOLD 边界。

## 12. 2026-10-20 文档级复核修订清单

本轮只修订文档（功能代码尚未开工，`src/lib/nail-personalization/` 与 `src/app/nail-analysis/` 均不存在），不涉及代码、接口、状态、数据或模型契约的实际变更。

**契约层**：`palmAspect` 增加手轴旋转归一化并修正量纲混用；新增 `OriginalImagePixels` 防止误用降采样图；`Recommendation.id` 定义确定性派生规则；`UserScenario` 新增 `nailCondition`/`hasAllergyHistory`（对齐资料汇编 §3.4 与 §8 结论）并确立 optional 三态语义；ITA 分档边界开闭（左开右闭）、底调判定优先级与量化边界、Monk 改为 ITA° 映射口径；skin-sampling 新增甲面自污染排除与采样数绝对下限，并明确「复用」实为复制常量、须加同步断言；hand-profile 新增重复甲面判据与 `suggestedFinger`/`palmAspect` 为 null 的处理；nail-health 给出权重取值并精确引用 `isSpecularHighlightPixel()`。

**规则层**：新增安全硬过滤（重劳作/薄软甲移除 long 组合）、同组合取最高权重（消除重叠重复计分）、组合分归一化；`color-undertone-warm-bright` 替换不符来源的「抹茶绿」；新增 neutral 专属规则；`color-ita-deep-jewel` 加质量门；新增甲面状况规则；规则表注明确 optional 字段禁止取反。

**测试与验收**：新增公平性、规则覆盖 meta-test、性能三个测试文件；补 ITA 边界开闭、旋转一致性、自污染排除、0 候选、琥珀文案同构等用例；补 Windows `PATH` 前提；里程碑补产物列与停止/回滚条件，并明确预注册假设的标定来源限制。

**文档自洽**：修正 §1 与 §9 的版本顺延表述冲突并改为动态口径；§3 状态行改为按 §1.1 据实登记；集成点补 `extract-mask-texture.ts` 与首页/Header 导航入口；新增 fallback 编排三处重复的同步责任；§5 明确改进计划开启时分析结果仍不外发；§6 新增当前可达性声明与 0 候选路径；§10 补三条风险。

**交叉一致性（与资料汇编对齐）**：[S30]（2025）与 [S31]（2024）不再合并表述；Monk 映射口径统一为 ITA°；`season` 降级为展示标签；问卷补齐资料汇编 §8 声称的甲面状况字段。
