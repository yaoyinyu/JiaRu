# 个性化美甲分析推荐 · 功能设计技术文档

> 设计日期：2026-10-19。配套资料汇编：`docs/nail-personalization-research.md`（规则来源、竞品与学术依据，引用编号 [Sxx] 均指该文档）。
> 本文档不进入技术白皮书正文、不顺延版本号；功能代码落地轮按白皮书 §12 模板登记，并顺延 v1.2.133 → v1.2.134。

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
  palmAspect: number | null;      // 五甲中心跨度近似（注释注明：候选不含掌部 landmarks，为近似量）
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
}

export interface ColorAdvice { family: string; presetNames: string[]; season?: "spring" | "summer" | "autumn" | "winter"; }
export interface RecommendationExplanation { ruleId: string; message: string; severity: "info" | "warning"; }
export interface Recommendation {
  id: string; rank: number; score: number;
  shape: NailShapeAdvice; length: LengthAdvice; colors: ColorAdvice;
  explanations: RecommendationExplanation[];
  confidence: "high" | "medium" | "low";
  requiresManualConfirmation: boolean;  // fallback/低置信/输入不足时为 true，UI 必须呈现琥珀提示
  ruleHits: string[];                   // 黄金测试锚点
}

export interface PersonalizationInput {
  image: ImagePixels;                       // 原图像素（肤色采样与健康启发式）
  candidates: readonly NailTextureCandidate[]; // 已回原图坐标
  backend: "model" | "fallback";            // PRODUCT HOLD 边界判定
  scenario: UserScenario;
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
- sRGB → XYZ（D65 白点）→ Lab 全流程；阈值常量集中在文件顶部（`ITA_BAND_BOUNDS = [55, 41, 28, 10, -30]`、`UNDERTONE_WARM_B = 14`、`UNDERTONE_OLIVE_A = 2` 等），便于运营调整与测试锁定。
- ITA° 公式与分档阈值依据 [S38]（同行评审）：>55° very-light、41–55° light、28–41° intermediate、10–28° tan、−30–10° brown、<−30° dark。
- `approximateMonkGrade`：按 L\* 线性分档近似（1≈L\*80 … 10≈L\*28），**头部注释必须声明「仅用于色号筛选沟通，不是标准 Monk 评估」**——Monk 标度为十级开源肤色标度 [S40]，v1 不做其官方映射。
- `classifyUndertone`：b\*>14 偏暖；b\*<4 且 a\*<0 偏冷；a\*>2 且 b\* 居中偏绿判橄榄；其余中性。方法学依据底调理论 [S54][S60] 与 Lab 通道语义 [S38]；**输出必须允许用户自评覆盖**（问卷 `selfReportedUndertone`），因为非受控拍照下底调测量不可靠 [S39]。

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
2. 肤色判定用**放宽版** YCbCr/RGB 规则（复用 `nail-partial-closeup-detection.ts` 的肤色规则思路并放宽阈值）——错误像素由逐通道**中位数**聚合吸收；
3. 有 `mask` 的候选按 mask 膨胀环取点；无 mask（mediapipe/局部近景路径）按候选椭圆几何取点；
4. 仅迭代候选包围盒，不扫全图（性能预算 <50ms，4096² 原图安全）；
5. `quality = 皮肤像素占比 × (有效候选数/期望候选数)`；`quality < 0.35` 时上游置 `skinTone = null` 并出 `skin_sampling_low_quality` 警告——**不允许低质量采样冒充测量结果**。

依据：环状证据法在项目内已有先例（局部近景检测的肤色邻环 [S 资料汇编 §1]）；ITA° 需在未受病变/污染区域计算的教训见 [S39]；光照偏差的系统性风险（阴影压低 ITA°）以 quality 门 + 页面提示缓解。

### 3.4 hand-profile.ts（手型/甲床分析）

```ts
export function analyzeHandProfile(candidates: readonly NailTextureCandidate[]): HandProfile;
```

1. 过滤无效候选（length/width ≤ 0、中心越界、重复甲面）；
2. 逐候选产 `NailBedMetrics`：`aspectRatio = length/width`，`relativeWidth = width / 五甲宽度中位数`；
3. `palmAspect = 五甲中心 x 跨度 / (y 跨度 + 甲长中位数)`——**近似量**（Gunasekera/IEEE 2024 的掌宽/掌长口径依赖手部关键点 [S30][S31]，v1 候选不含掌部 landmarks，不可复现，不假装精确）；
4. 分类常量表 `HAND_SHAPE_THRESHOLDS`：
   - `wide-short`：`medianNailAspect < 1.25 && palmAspect > 0.72`
   - `narrow-long`：`medianNailAspect > 1.55 && palmAspect < 0.62`
   - `slim-tapered`：`thumbRatio > 0.78 && medianNailAspect > 1.40`
   - 其余 `balanced`
5. `completeness < 0.6` → 警告 `hand_profile_insufficient_candidates`，推荐置信度封顶 medium。

### 3.5 nail-health.ts（指甲健康启发式，严格限定）

```ts
export function analyzeNailHealthHeuristic(
  image: ImagePixels,
  candidates: readonly NailTextureCandidate[] // 仅使用带 mask 的候选
): NailHealthHeuristic | null;                 // 无 mask 候选 → null
```

- `colorUniformity`：mask 前景 Lab L\* 的稳健离散度（MAD）归一化；
- `highlightRatio`：与 `extract-mask-texture.ts` 同款高光判据（L\* 高且低饱和）的像素占比；
- `textureStreaking`：沿 `candidate.angle` 方向的梯度均值 / 垂直方向梯度均值；
- `score = round(100 × (w1×均匀度 + w2×(1−高光占比) + w3×(1−条纹)))`，权重为文件顶部常量；
- **硬约束**：输出恒带 `heuristicOnly: true`；present 层文案固定含「启发式观察，不构成医疗或诊断结论」；**不做任何疾病分类**。

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
1. 甲型候选分 = 命中 shape 规则按 `shape+length` 组合聚合的权重和；色系候选分 = 命中 color 规则按 `family` 聚合的权重和；
2. 甲型 Top-3 × 色系 Top-3 按「甲型分 + 色系分」降序组成推荐组合，去重，截断 topK（默认 3）；
3. `explanations` = 命中规则文案按权重降序（severity：覆盖类规则如重体力/职场标 warning，其余 info）；`ruleHits` 记录规则 id；
4. 置信度：`backend === "fallback"` 或存在低置信候选 → `requiresManualConfirmation = true` 且封顶 medium；`completeness < 0.6` 或 `skin === null` 再降一档；
5. 用户自评底调优先：调用方组 `SkinToneAnalysis` 时以 `selfReportedUndertone` 覆盖 `undertone` 并标记来源；规则无感，文案区分「测得/你自评」。

**完整规则表**（来源编号见资料汇编 §3；presetNames 全部引用 `src/lib/utils.ts` 既有 20 色，测试强制校验存在性）：

甲型规则（NAIL_SHAPE_RULES，10 条）：

| id | 权重 | 条件 | 建议 | 解释要点 |
| --- | --- | --- | --- | --- |
| shape-heavy-labor-squoval | 4 | manualLabor=heavy | squoval/short | 方圆形短甲边角厚不易劈裂，洗漱日常耐用（覆盖规则） |
| occasion-work-squoval | 3 | occasion=work | squoval/short | 职场通勤低keys干扰，短方圆稳重不突兀 |
| style-low-maintenance-round | 3 | style=low-maintenance | round/short | 圆形长出最自然、免频繁修型 |
| shape-wide-short-round | 3 | shape=wide-short && lengthPreference≠long | round/short | 甲床偏短宽，圆形收敛两侧显修长 |
| shape-narrow-long-oval | 3 | shape=narrow-long && occasion≠party | oval/medium | 甲床偏长窄，椭圆顺应自然比例 |
| shape-slim-tapered-almond | 2 | shape=slim-tapered | almond/medium | 拇指相对窄+甲面长，杏仁延伸优雅线条 |
| shape-balanced-squoval | 2 | shape=balanced | squoval/medium | 比例均衡，方圆形百搭耐用 |
| occasion-wedding-oval | 2 | occasion=wedding && lengthPreference≠short | oval/medium | 婚礼中长椭圆/杏仁衬纱与戒指 |
| occasion-party-bold-almond | 2 | occasion=party && style=bold | almond/long | 派对+夸张风格，杏仁长甲有存在感；长度以日常可承受为准 |
| shape-short-bed-round | 2 | medianNailAspect<1.2 | round/short | 甲床偏短（含啃咬甲），圆形不需长度基底 |

颜色规则（COLOR_RULES，13 条）：

| id | 权重 | 条件 | 色系（presetNames） | 季型 |
| --- | --- | --- | --- | --- |
| occasion-work-nude | 4 | occasion=work | 职场裸色：裸粉色/裸色/奶茶色 | — |
| occasion-wedding-elegant | 4 | occasion=wedding | 婚礼优雅色：裸粉色/纯白色/银色 | — |
| color-undertone-warm-rich | 3 | undertone=warm && itaBand∈{brown,tan} | 暖调浓郁色：酒红色/焦糖色/樱桃红 | autumn |
| color-undertone-cool-soft | 3 | undertone=cool | 冷调柔雾色：雾霾蓝/薰衣草紫/豆沙红 | summer |
| color-undertone-warm-bright | 3 | undertone=warm && itaBand∈{very-light,light} | 暖调明亮色：珊瑚粉/橘色/抹茶绿 | spring |
| color-ita-deep-jewel | 3 | itaBand=dark | 宝石亮色：玫红色/深蓝色/金色 | winter |
| occasion-party-bold | 3 | occasion=party && style=bold | 派对闪耀色：亮片银/金色/黑色 | — |
| color-undertone-olive-earth | 2 | undertone=olive | 大地浓郁色：焦糖色/抹茶绿/奶茶色 | autumn |
| color-ita-fair-soft | 2 | itaBand∈{very-light,light} && undertone∉{warm} | 柔粉淡紫：裸粉色/豆沙红/薰衣草紫 | summer |
| occasion-date-romantic | 2 | occasion=date | 约会浪漫色：酒红色/豆沙红/樱桃红 | — |
| occasion-vacation-bright | 2 | occasion=vacation | 度假明亮色：珊瑚粉/橘色/抹茶绿 | — |
| occasion-daily-safe | 1 | occasion=daily | 日常安全色：裸粉色/豆沙红/珊瑚粉 | — |
| length-optical-light | 1 | lengthPreference=short ‖ medianNailAspect<1.2 | 浅裸拉长色：裸粉色/裸色/纯白色 | — |

规则完备性说明：`skin === null` 时全部肤色规则自动失效（`when` 首判 `skin !== null`），推荐降级为纯场景/风格/手型驱动并出 `skin_tone_unavailable_color_fallback` 提示；每条规则至少一个命中 fixture（测试强制，防静默漂移）。

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
- `auxiliaryAnalysisNotice` 与既有 `auxiliaryDetectionNotice` 同构：fallback 时返回「当前为辅助定位结果，甲面边界未经正式模型确认；分析结论仅供参考，请结合实物效果判断。」
- 指甲健康文案固定含「启发式观察，不构成医疗或诊断结论」；肤色文案注明「非受控拍摄，ITA° 仅供色号筛选参考」。

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

---

## 4. 集成点清单

| 集成点 | 文件 | 改动性质 |
| --- | --- | --- |
| 识别直连 | `src/lib/nail-texture-recognition/index.ts`、`input-scaling.ts` | 只读调用，**禁改** |
| 上传校验 | `src/lib/image-upload-validation.ts` | 只读复用 |
| 新页面 | `src/app/nail-analysis/page.tsx`（AppShell + 状态机 idle→analyzing→result） | 新建 |
| 新组件 | `src/components/NailAnalysisForm.tsx`（问卷）、`src/components/NailAnalysisResult.tsx`（推荐卡+琥珀提示） | 新建 |
| 出站消费 | `src/app/editor/page.tsx` 增加 `?preset=` 消费（约 20 行，照 `?gallery=` 模式） | 小改 |
| 隐私页 | `src/app/privacy/page.tsx` 功能枚举增加「个性化分析推荐 · 默认本地」一行 | 小改 |
| 禁改清单 | 识别管线全部、`nail-hand-geometry-detection.ts`、`nail-partial-closeup-detection.ts`、`NailArtPicker.tsx`、`ar-tryon/*`、`model/*`、`public/models/*` | **零改动**（与纹理模型 Goal 隔离） |

新页面检测编排按 `/device-benchmark` 先例自持一份精简编排（worker 识别 → remap → fallback 链），不抽取共享函数、不改 NailArtPicker，并在注释注明重复原因。

---

## 5. 隐私合规

- 全部计算在浏览器本地：识别（Worker/主线程）、肤色采样（canvas getImageData）、规则引擎（纯函数）；**不新增任何上传通道**，「用户改进计划」开关与本功能无关（白皮书 §2/§10）；
- ImageBitmap / canvas / objectURL 在取消与卸载时释放（照白皮书 §10 资源释放清单）；
- 隐私判断依据：矩阵中仅 Cutie Nails 强调照片仅本地 [S15]——本地处理既是项目原则也是竞品空位，UI 应明示。

---

## 6. PRODUCT HOLD 边界（必须如实呈现）

1. `backend === "fallback"` 或任一候选 `confidence === "low"`：页面级琥珀声明 + 每条推荐 `requiresManualConfirmation = true`；文案统一「辅助分析结果，请结合实物效果判断」，**禁止「自动分析完成/精准推荐」话术**；
2. 无 mask 候选（mediapipe/局部近景路径）：`nailHealth = null`，UI 隐藏健康评分而非展示猜测值，警告 `nail_health_requires_mask`；
3. 肤色采样质量不足：`skinTone = null`，颜色推荐降级为场合/风格规则，警告 `skin_sampling_low_quality`；
4. 以上全部复用既有 warning code 模式（参考 `nail-art-picker-quality.ts`），不发明新状态机。

---

## 7. 测试计划

测试文件（`tests/*.test.ts`，node --test + node:assert/strict，从 `../src/lib/nail-personalization/...` 导入；合成 fixture 全部内存构造，不提交二进制）：

| 测试文件 | 覆盖 | 关键用例 |
| --- | --- | --- |
| nail-personalization-color-science.test.ts | Lab/ITA°/Monk/底调/ΔE | 已知 Lab 的 sRGB fixture 断言 ITA° 容差 ±1°；分档边界 55/41/28/10/−30；Monk 分档单调；底调边界；非法输入 null |
| nail-personalization-skin-sampling.test.ts | 肤色环采样 | 已知肤色环+异色甲面+背景噪点合成图 → 聚合 Lab 复现已知值（中位数抗噪）；mask/椭圆两路径；候选贴边；皮肤像素全滤除 → quality=0 |
| nail-personalization-hand-profile.test.ts | 手型分类 | 短宽→wide-short、长窄→narrow-long、拇指宽→slim-tapered、混合→balanced；候选<3 → completeness 低+警告；零尺寸/越界候选被过滤 |
| nail-personalization-nail-health.test.ts | 健康启发式 | 均匀色 mask→高均匀低条纹；条纹 mask→streaking 升高；高光 mask→highlightRatio；无 mask→null；**断言恒含 heuristicOnly 且文案无医疗措辞** |
| nail-personalization-rules.test.ts | 规则引擎黄金样 | 固定 (HandProfile, Skin, Scenario)→精确 top-K 推荐 id 与 ruleHits、explanation 逐字断言；fallback→requiresManualConfirmation；skin=null 降级路径；规则覆盖率 100%（每条规则有命中 fixture）；规则 id 唯一；presetNames 全部存在于 PRESET_COLORS |
| nail-personalization-present.test.ts | 文案层 | severity 分级、dedupe、琥珀 notice、health/skin 为 null 时的隐藏语义 |
| nail-personalization-bridge.test.ts | 参数桥接 | 合法往返；非法 preset/shape 拒绝（照 tests/gallery-bridge.test.ts 模式） |
| nail-personalization.test.ts | 编排入口 | 端到端合成输入→PersonalizationResult 全字段断言；fallback+低质量采样组合降级链 |

验证命令（Windows 必须 `npm.cmd`，串行）：`npm.cmd test` → `npm.cmd run typecheck` → `npm.cmd run typecheck:tests` → `npm.cmd run lint` →（页面落地轮）`npm.cmd run build`。新测试文件被 `tests/*.test.ts` 通配自动纳入。

---

## 8. 里程碑与验收标准（预注册）

| # | 里程碑 | 完成标准 |
| --- | --- | --- |
| M1 | color-science.ts + 测试 | 上述色彩科学用例全过；串行 test/typecheck/typecheck:tests/lint 全绿 |
| M2 | hand-profile.ts + 测试 | 四类手型合成样本分类正确；候选不足/无效输入路径有警告且 completeness 正确 |
| M3 | skin-sampling.ts + 测试 | 合成环图复现已知肤色 Lab（容差内）；两路径/贴边/全滤除用例通过 |
| M4 | nail-health.ts + 测试 | 均匀/条纹/高光 fixture 指标方向正确；无 mask→null；heuristicOnly 恒真且无医疗措辞（断言） |
| M5 | rules.ts + present.ts + 测试 | 黄金样例逐字通过；覆盖率 100%、id 唯一、presetNames 有效；fallback→requiresManualConfirmation；skin=null 降级路径 |
| M6 | 页面与桥接 | /nail-analysis 本地图走通「识别→分析→问卷→推荐」；fallback 琥珀声明必现；/editor?preset= 预涂生效；/privacy 增加一行；npm.cmd run build 通过 |
| M7 | 文档同步 | 白皮书 §3 行 + §4.6 小节 + v1.2.133→v1.2.134 与 dev-log「白皮书 v1.2.134」同一次编辑；README 功能概览/隐私小节同步；全量串行验证通过 |

---

## 9. 白皮书登记草稿（功能落地轮使用）

**§3 状态表新增行**：

```md
| 个性化美甲分析推荐 | `/nail-analysis` | 待验证（纯规则启发式） | 浏览器本地分析手型/甲床比例、肤色（ITA°与底调）与指甲健康启发式，结合场景问卷由规则引擎推荐甲型、色系与长度并附中文解释；全部本地计算不上传。候选未经正式模型确认时以琥珀辅助提示标注，不算自动分析成功 |
```

**§4.6 小节**（照 §4.4 /ai-generate 先例，插在 §4.5 之后）：

```md
### 4.6 `/nail-analysis` 个性化分析推荐

状态：待验证（纯规则启发式，不引入新模型训练）。

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

版本与日志：落地轮顺延 v1.2.133 → **v1.2.134**，当日 dev-log 以「白皮书 v1.2.134」标记与白皮书头部同一次编辑同步；若同轮更新 /privacy 与 README，按 AGENTS.md 在提交前一并同步（无用户明确要求不提交）。

---

## 10. 风险与边界

1. **纯规则推荐的定位**：输出是「可解释的启发式建议」而非个性化保证；卡片必带解释与置信度；学术指标（90%/95%/86.5%）属其受控实验条件，不可迁移为本产品话术。
2. **肤色测量的光照/设备偏差**：ITA° 源于受控条件 [S38]；阴影/差光照系统性压低 ITA° [S39]；Fitzpatrick/Monk 存在偏见文献 [S33][S38][S40]。缓解：中位数聚合、quality<0.35 隐藏、用户自评底调覆盖、Monk 仅作色号筛选沟通、页面明示「非受控拍摄仅供参考」。
3. **指甲健康启发式的医疗边界**：只做均匀度/高光/条纹三类观察，不做疾病分类 [S32][S34][S37]；固定非医疗声明，测试断言文案。
4. **手型近似的局限**：v1 仅用候选派生比例；掌宽/掌长口径不可复现 [S30][S31]；landmark 透传列为后续可选，不触碰现有管线。
5. **PRODUCT HOLD 隔离**：不训练、不改模型、不改识别链路；辅助定位输入未经人工确认时如实标注。
6. **规则表漂移**：规则为 TS 常量 + 黄金测试；运营调整必须同步测试，以测试锁防静默漂移。
7. **资料时效**：市场数据与竞品结论带口径年份；落地轮若与资料冲突，以可复现当前事实为准（白皮书 §1.2 优先级原则同样适用于设计文档维护）。

---

## 11. 关联文档

- `docs/nail-personalization-research.md`：竞品矩阵、学术注释、领域知识库（规则来源）、技术方法、市场数据、公开数据集、来源 URL 全清单。
- `docs/technical-whitepaper.md`：§2（本地处理原则）、§3（状态总表）、§4.4（页面登记先例）、§6（识别接口）、§10（隐私）、§12（登记模板）。
- `docs/nail-texture-current-goal.md`：纹理模型 Goal——本功能与其零交集（不训练、不改模型），但推荐功能消费其识别输出，须遵守 §6 的 HOLD 边界。
