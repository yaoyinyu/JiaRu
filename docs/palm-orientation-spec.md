# AR 手心/手背朝向检测技术方案

> **目标**：在 AR 试戴中区分手心和手背，仅在**手背朝向镜头**时绘制美甲纹理。
>
> **创建时间**：2026-06-23
> **状态**：待实现

---

## 1. 问题分析

### 1.1 现状
当前 `ArView.tsx` 的 `paintNails()` 函数对检测到的每只手直接绘制指甲纹理，不区分手心/手背朝向。用户手心面向镜头时也会被贴上美甲纹理，不符合真实物理（指甲只长在手背侧）。

### 1.2 MediaPipe Hands 输出特性

MediaPipe Hands 返回 21 个关键点，每个点包含：
- `x, y`：归一化图像坐标 [0, 1]
- `z`：**相对于手腕的深度偏移**（非绝对距离）
  - 负值 = 该点比手腕更靠近镜头
  - 正值 = 该点比手腕更远离镜头
  - 原始 z 精度有限，存在帧间噪声

关键点索引：
```
0: 手腕 (WRIST)
1-4: 拇指 (CMC, MCP, IP, TIP)
5-8: 食指 (MCP, PIP, DIP, TIP)
9-12: 中指 (MCP, PIP, DIP, TIP)
13-16: 无名指 (MCP, PIP, DIP, TIP)
17-20: 小指 (MCP, PIP, DIP, TIP)
```

### 1.3 解剖学事实

- **手背朝镜头**：指关节（PIP/MCP）凸起，朝向镜头 → PIP 点 z 值更负（靠近镜头）
- **手心朝镜头**：指腹凸起，指尖朝向镜头 → TIP 点 z 值比 PIP 更负
- **手掌平面**：手腕(0) + 食指根(5) + 小指根(17) 三点定义手掌平面，法向量方向区分正反面

---

## 2. 技术方案总览

| 方案 | 原理 | 优点 | 缺点 | 采纳 |
|------|------|------|------|:----:|
| A. 手掌法向量 | 手掌三点叉积法向量 z 符号 | 纯几何、计算快、物理意义明确 | z 噪声敏感 | ✅ 主方案 |
| B. 关节深度投票 | PIP vs TIP z 差值五指投票 | 简单、局部特征 | 单指噪声大 | ✅ 辅助验证 |
| C. handedness 推理 | 左右手 + 拇指位置 | 不依赖 z | 镜像/旋转不可靠 | ❌ |
| D. ML 分类器 | 训练轻量分类器 | 最准确 | 过度工程、需训练数据 | ❌ |
| E. 拇指位置法 | 拇指在手掌的左右侧 | 不依赖 z | 依赖 handedness | ❌ |

**最终方案：A + B 融合**
- 方案 A 计算手掌法向量，作为主判断
- 方案 B 五指投票作为交叉验证
- 两者一致 → 高置信度，直接渲染或跳过
- 两者不一致 → 低置信度，采用 A 结果但记录冲突计数

---

## 3. 详细技术设计

### 3.1 方案 A：手掌法向量法

#### 3.1.1 原理

用三个手掌关键点构建两个手掌内向量，叉积得到手掌法向量：

```
P0 = landmark[0]  // 手腕
P5 = landmark[5]  // 食指 MCP（食指根部）
P17 = landmark[17] // 小指 MCP（小指根部）

v1 = P5 - P0    // 手腕→食指根
v2 = P17 - P0   // 手腕→小指根

normal = v1 × v2   // 手掌法向量（3D 叉积）
```

#### 3.1.2 判断逻辑

MediaPipe z 坐标：负值=靠近镜头，正值=远离镜头。

- **手背朝镜头**（指甲可见）：手掌法向量指向镜头 → `normal.z < 0`
- **手心朝镜头**（掌纹可见）：手掌法向量背离镜头 → `normal.z > 0`
- **侧手**（法向量近似平行于镜头平面）：`|normal.z|` 极小 → 模糊态，不渲染

#### 3.1.3 阈值设计

```typescript
const PALM_NORMAL_Z_THRESHOLD = -0.01;  // 法向量 z < 此值 = 手背朝镜头
const PALM_NORMAL_AMBIGUOUS = 0.005;    // |z| < 此值 = 侧手，模糊态
```

- `normal.z < -0.01` → **手背朝镜头** → 渲染美甲 ✅
- `normal.z > 0.01` → **手心朝镜头** → 不渲染 ❌
- `|normal.z| <= 0.01` → **侧手/过渡态** → 不渲染（安全降级）

#### 3.1.4 时序平滑

法向量 z 分量帧间抖动会导致闪烁。引入 EMA 平滑：

```typescript
// smoothPalmNormalZ 初始 NaN
smoothPalmNormalZ = ema(smoothPalmNormalZ, rawNormalZ)  // EMA_ALPHA=0.3（比指尖平滑更保守）
```

#### 3.1.5 验收标准

| # | 验收项 | 方法 | 通过标准 |
|---|--------|------|----------|
| A1 | 手背朝镜头时渲染美甲 | 手背朝摄像头张开五指 | 美甲纹理出现在指甲位置 |
| A2 | 手心朝镜头时不渲染 | 翻转手掌，手心朝摄像头 | Canvas 上无美甲纹理 |
| A3 | 翻手过渡无闪烁 | 缓慢翻转手掌 180° | 过渡期间无闪烁/跳变，平滑切换 |
| A4 | 侧手安全降级 | 手掌垂直于镜头（刀手姿势） | 不渲染美甲（安全降级） |
| A5 | console.log 输出法向量数据 | 开 DevTools Console | 每帧打印 `{nz: number, decision: "dorsum"|"palm"|"ambiguous"}` |

---

### 3.2 方案 B：关节深度投票法

#### 3.2.1 原理

手背朝镜头时，指关节（PIP, 索引 2/6/10/14/18）比指尖（TIP, 索引 4/8/12/16/20）更靠近镜头 → `PIP.z < TIP.z`（z 更负）。

五指各自比较 PIP 和 TIP 的 z 差值，投票决定：

```typescript
for (let f = 0; f < 5; f++) {
  const pipZ = lm[PIPS[f]].z;  // PIP 关节 z
  const tipZ = lm[TIPS[f]].z;  // 指尖 z
  const dz = tipZ - pipZ;      // 正 = PIP 更靠近镜头 = 手背朝镜头
  if (dz > 0.005) dorsumVotes++;
  else if (dz < -0.005) palmVotes++;
  // |dz| <= 0.005 弃权
}
```

#### 3.2.2 判断逻辑

- `dorsumVotes >= 3`（5 指中多数） → 倾向手背
- `palmVotes >= 3` → 倾向手心
- 其他 → 弃权

#### 3.2.3 验收标准

| # | 验收项 | 方法 | 通过标准 |
|---|--------|------|----------|
| B1 | 手背时多数投票为 dorsum | 手背朝镜头 | `dorsumVotes >= 3` |
| B2 | 手心时多数投票为 palm | 手心朝镜头 | `palmVotes >= 3` |
| B3 | 投票结果与方案 A 一致 | 同时打印两者 | `decision === voteResult`（>=90% 帧） |
| B4 | console.log 输出投票详情 | DevTools | `{dorsum: N, palm: N, abstain: N}` |

---

### 3.3 融合决策逻辑

```typescript
function shouldRenderNails(lm: Landmark[], smoothNormalZ: number): {
  render: boolean;
  confidence: "high" | "low";
  reason: string;
} {
  // 方案 A：法向量判断
  const isDorsumByNormal = smoothNormalZ < -PALM_NORMAL_Z_THRESHOLD;
  const isPalmByNormal = smoothNormalZ > PALM_NORMAL_Z_THRESHOLD;
  const isAmbiguousByNormal = !isDorsumByNormal && !isPalmByNormal;

  // 方案 B：投票判断
  let dorsumVotes = 0, palmVotes = 0;
  for (let f = 0; f < 5; f++) {
    const dz = lm[TIPS[f]].z - lm[PIPS[f]].z;
    if (dz > 0.005) dorsumVotes++;
    else if (dz < -0.005) palmVotes++;
  }
  const isDorsumByVote = dorsumVotes >= 3;
  const isPalmByVote = palmVotes >= 3;

  // 融合
  if (isAmbiguousByNormal) {
    return { render: false, confidence: "low", reason: "侧手/过渡态" };
  }
  if (isDorsumByNormal && isDorsumByVote) {
    return { render: true, confidence: "high", reason: "双方案一致：手背" };
  }
  if (isPalmByNormal && isPalmByVote) {
    return { render: false, confidence: "high", reason: "双方案一致：手心" };
  }
  // 不一致 → 采用 A 结果，降低置信度
  return {
    render: isDorsumByNormal,
    confidence: "low",
    reason: `方案不一致 A=${isDorsumByNormal ? "dorsum" : "palm"} B votes d${dorsumVotes}/p${palmVotes}`,
  };
}
```

#### 3.3.1 验收标准

| # | 验收项 | 方法 | 通过标准 |
|---|--------|------|----------|
| C1 | 手背双方案一致时渲染 | 手背朝镜头 | `confidence: "high"` + 渲染 |
| C2 | 手心双方案一致时不渲染 | 手心朝镜头 | `confidence: "high"` + 不渲染 |
| C3 | 不一致时采用方案 A | 刻意做侧手过渡 | `confidence: "low"` + 按 A 结果行动 |
| C4 | console.log 输出融合决策 | DevTools | 每帧打印 `{render, confidence, reason}` |

---

### 3.4 UI 反馈增强

在现有诊断面板中增加朝向指示：

- 手背朝镜头 → 显示绿色 "🖐️ 手背" 标识
- 手心朝镜头 → 显示橙色 "✋ 手心" 标识
- 模糊态 → 显示灰色 "🤚 侧手" 标识

即使 `status === "ready"`，也显示一个小的朝向状态指示器（非侵入式）。

#### 3.4.1 验收标准

| # | 验收项 | 方法 | 通过标准 |
|---|--------|------|----------|
| D1 | 手背时显示绿色手背标识 | 手背朝镜头 | 底部状态栏显示 "🖐️ 手背" |
| D2 | 手心时显示橙色手心标识 | 手心朝镜头 | 底部状态栏显示 "✋ 手心" |
| D3 | 侧手时显示灰色标识 | 侧手姿势 | 底部状态栏显示 "🤚 侧手" |
| D4 | 标识不遮挡美甲渲染 | 手背渲染时 | 标识在底部，美甲在中央，无重叠 |

---

### 3.5 性能影响评估

#### 3.5.1 计算开销

| 操作 | 复杂度 | 预估耗时 |
|------|--------|----------|
| 法向量叉积（3 个减法 + 6 个乘法） | O(1) | <0.01ms |
| 五指 z 差值投票（5 次减法 + 5 次比较） | O(1) | <0.01ms |
| EMA 平滑（1 次加法 + 1 次乘法） | O(1) | <0.01ms |
| **总增量** | O(1) | **<0.03ms/帧** |

**结论**：对帧率无可感知影响（<0.1% 增量）。

#### 3.5.2 验收标准

| # | 验收项 | 方法 | 通过标准 |
|---|--------|------|----------|
| E1 | 帧率不下降 | DevTools Performance | 加入朝向检测前后帧率差 < 1fps |
| E2 | 无内存泄漏 | DevTools Memory | 连续运行 5 分钟，堆内存无持续增长 |

---

## 4. 实现步骤

### Step 1：添加手掌法向量计算函数

在 `ArView.tsx` 中新增 `computePalmNormalZ(lm: Landmark[]): number` 函数。

**输入**：21 个关键点
**输出**：法向量 z 分量（已 EMA 平滑）

**实现要点**：
- 用 `lm[0]`（手腕）、`lm[5]`（食指根）、`lm[17]`（小指根）构建手掌平面
- 叉积公式：`nz = v1.x * v2.y - v1.y * v2.x`（只需 z 分量）
  - `v1 = P5 - P0`, `v2 = P17 - P0`
  - `nz = v1.x * v2.y - v1.y * v2.x`（注意：这是 2D 叉积的 z 分量，但 MediaPipe z 是深度，不是 3D 空间 z）
  - **修正**：需要完整 3D 叉积
  - `v1 = (P5.x-P0.x, P5.y-P0.y, P5.z-P0.z)`
  - `v2 = (P17.x-P0.x, P17.y-P0.y, P17.z-P0.z)`
  - `normal = v1 × v2`
  - `nz = v1.y * v2.z - v1.z * v2.y`（叉积 z 分量）
  - **再修正**：法向量 z 分量的物理意义是法向量在镜头轴方向的投影
  - 但 MediaPipe 的 z 是相对深度，不是世界坐标 z
  - 实际上需要用 3D 叉积的 **z 分量**，因为 z 轴对应深度方向
  - `nz = v1.x * v2.y - v1.y * v2.x` ← 这个是**屏幕平面法向**的 z 分量
  - 不对。让我重新推导。

**正确推导**：

3D 叉积 `n = v1 × v2`：
```
n.x = v1.y * v2.z - v1.z * v2.y
n.y = v1.z * v2.x - v1.x * v2.z
n.z = v1.x * v2.y - v1.y * v2.x
```

`n.z` 是法向量在 **z 轴（深度方向）** 的分量。但由于 MediaPipe 的 z 是相对深度（不是绝对世界坐标），`n.z` 的物理含义是法向量在深度轴上的投影。

**但这里有个微妙的问题**：`n.z = v1.x * v2.y - v1.y * v2.x` 只用了 x 和 y 分量，完全没用到 z。这意味着 `n.z` 实际上是 2D 叉积的结果，反映的是 v1 和 v2 在图像平面上的旋转关系，而不是真正的 3D 深度信息。

**真正需要的是法向量的深度分量**，应该看 `n.z` 是否使用了深度信息。观察公式：
- `n.x = v1.y * v2.z - v1.z * v2.y`  ← 用了 z
- `n.y = v1.z * v2.x - v1.x * v2.z`  ← 用了 z
- `n.z = v1.x * v2.y - v1.y * v2.x`  ← **没用 z！**

所以 `n.z` 不能区分手心/手背！我们需要的是法向量在**镜头方向**的投影，即法向量本身（3D）与镜头方向的点积。

**正确方法**：
1. 计算 3D 法向量 `n = v1 × v2`（完整 3D）
2. 镜头方向假设为 `(0, 0, -1)`（朝向用户）
3. 点积 `dot = n.x * 0 + n.y * 0 + n.z * (-1) = -n.z`
4. 但 `n.z = v1.x * v2.y - v1.y * v2.x` 不含深度信息

**关键问题**：MediaPipe 的 z 坐标是"相对手腕的深度"，不是世界坐标 z。叉积的 z 分量只反映图像平面内的旋转方向，不反映 3D 朝向。

**修正方案**：应该看法向量的 **x 和 y 分量**（它们包含 z 深度信息），或者用另一种方法。

实际上，更直接的方法是：**直接用 z 深度差值判断**。

#### 修正后的方案 A（法向量法 v2）

用手掌三个点的 z 值构建深度平面：

```
P0 = lm[0]   // 手腕
P5 = lm[5]   // 食指根
P9 = lm[9]   // 中指根
P17 = lm[17] // 小指根

// 手掌中心的 z 深度（平均）
palmZ = (P0.z + P5.z + P9.z + P17.z) / 4

// 手指关节中心的 z 深度（平均）
knuckleZ = (lm[2].z + lm[6].z + lm[10].z + lm[14].z + lm[18].z) / 5

// 关节比手掌中心更靠近镜头 → 手背朝镜头
dz = palmZ - knuckleZ  // 正 = 关节凸起 = 手背
```

**物理意义**：手背朝镜头时，指关节（PIP）凸起，z 值比手掌中心更负（更靠近镜头）。手心朝镜头时，手掌中心更靠近镜头，关节相对凹下。

#### 修正后的方案 B（指尖-关节 z 差投票）

与之前相同，但更可靠：
```
dz = PIP.z - TIP.z
// 手背朝镜头：PIP 更凸 → PIP.z < TIP.z → dz < 0
// 等等，这个逻辑需要重新验证...
```

**重新推理**：
- z 负 = 靠近镜头
- 手背朝镜头：PIP 关节凸起 → PIP 更靠近镜头 → PIP.z 更负
- 所以 `PIP.z < TIP.z`（PIP 的 z 更负）→ 手背
- `dz = TIP.z - PIP.z`，正值 = PIP 更靠近镜头 = 手背 ✅

---

### 修正后的技术方案（最终版）

经过以上推理修正，最终方案如下：

#### 方案 A（主）：手掌深度差法

比较手掌中心与指关节区域的平均 z 深度：
- `palmZ` = 手腕(0) + 食指根(5) + 中指根(9) + 小指根(17) 的 z 平均
- `knuckleZ` = PIP 关节(2,6,10,14,18) 的 z 平均
- `depthDiff = palmZ - knuckleZ`
  - `> 0`：关节比手掌中心更靠近镜头 → **手背朝镜头** ✅
  - `< 0`：手掌中心比关节更靠近镜头 → **手心朝镜头** ❌

#### 方案 B（辅）：指尖-PIP z 差投票

五指各自比较 TIP 和 PIP 的 z 差值：
- `dz = TIP.z - PIP.z`
  - `> 0`：PIP 更靠近镜头 → 手背投票
  - `< 0`：TIP 更靠近镜头 → 手心投票

#### 融合决策

两者一致 → 高置信度执行；不一致 → 采纳方案 A 结果，降低置信度。

---

## 5. 验收计划

### 5.1 单元测试（手工）

| 测试场景 | 操作 | 预期结果 | 验收方法 |
|----------|------|----------|----------|
| T1: 手背朝镜头 | 手背正对摄像头，五指张开 | 渲染美甲 | 截图 + console.log `{render:true, confidence:"high"}` |
| T2: 手心朝镜头 | 翻掌，手心正对摄像头 | 不渲染美甲 | 截图 + console.log `{render:false, confidence:"high"}` |
| T3: 缓慢翻手 | 从手背缓慢翻到手心 | 平滑切换，无闪烁 | 录屏观察 + console.log 无频繁 render 切换 |
| T4: 侧手 | 手掌垂直于镜头 | 不渲染（安全降级） | console.log `{render:false, confidence:"low"}` |
| T5: 远距离手背 | 手离镜头较远（手小） | 仍然渲染 | console.log `{render:true}` |
| T6: 近距离手背 | 手贴近镜头 | 仍然渲染 | console.log `{render:true}` |
| T7: 多帧稳定性 | 保持手背姿势 10 秒 | 无闪烁/跳变 | console.log 连续 300 帧中 render=true 占比 > 95% |

### 5.2 回归测试

| 测试 | 操作 | 预期 |
|------|------|------|
| R1: ESLint 通过 | `npx eslint .` | ExitCode 0 |
| R2: Build 通过 | `npm run build` | PASS |
| R3: 原有功能不受影响 | 编辑器/图库/AI 页面正常 | 无报错 |

### 5.3 证据要求

每项验收必须提供**直接证据**：

- **截图/录屏**：证明视觉行为正确
- **console.log 输出**：证明内部逻辑判断正确
- **ESLint/Build 输出**：证明代码质量达标

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|----------|
| z 坐标噪声导致抖动 | 高 | 中 | EMA 平滑（α=0.3）+ 阈值滞回（避免临界值反复跳变） |
| 侧手判断模糊 | 中 | 低 | 安全降级（不渲染），UI 提示用户调整手势 |
| 远距离 z 精度下降 | 中 | 中 | 距离过远时不渲染 + UI 提示"请将手靠近镜头" |
| 不同光照影响 z 检测 | 低 | 低 | MediaPipe z 基于几何模型不依赖光照，风险极低 |
| 拇指 z 不可靠 | 中 | 低 | 拇指投票权重降低或排除（拇指 z 噪声大于其他指） |

---

## 7. 阈值参数汇总

| 参数 | 值 | 说明 |
|------|-----|------|
| `PALM_DEPTH_THRESHOLD` | 0.003 | 手掌-关节深度差阈值，>此值=手背 |
| `PALM_DEPTH_AMBIGUOUS` | 0.001 | \|深度差\| < 此值 = 模糊态 |
| `FINGER_Z_VOTE_THRESHOLD` | 0.002 | 单指 z 差投票阈值 |
| `EMA_ALPHA_NORMAL` | 0.3 | 法向量/深度差 EMA 平滑因子 |
| `HYSTERESIS_MARGIN` | 0.001 | 滞回余量，防止临界值反复跳变 |

> ⚠️ 以上参数为初始值，需通过实际测试调优。

---

## 8. 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `src/components/ArView.tsx` | 新增 `computePalmOrientation()` 函数、融合决策逻辑、UI 朝向指示器 |
| `docs/palm-orientation-spec.md` | 本文档 |
| `dev-log/2025-06-23.md` | 追加开发日志 |

---

## 9. 实现顺序

1. **Step 1**：实现 `computePalmOrientation()` 函数（方案 A + B） → 验收 A1-A5, B1-B4
2. **Step 2**：实现融合决策逻辑 `shouldRenderNails()` → 验收 C1-C4
3. **Step 3**：集成到 `paintNails()` 渲染流程 → 验收 T1-T7
4. **Step 4**：添加 UI 朝向指示器 → 验收 D1-D4
5. **Step 5**：性能验证 + 回归测试 → 验收 E1-E2, R1-R3
6. **Step 6**：Git commit + 更新 dev-log
