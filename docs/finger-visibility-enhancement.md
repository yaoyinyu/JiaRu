# 逐指指甲可见性增强 — 多信号融合方案

**创建时间**: 2026-06-24
**实现目标**: 当手部偏转时，仅对露出指甲的手指贴上美甲纹理，手心侧手指不贴
**对应组件**: `src/components/ArView.tsx`

---

## 1. 问题分析

### 1.1 当前方案

当前 `isNailVisible()` 仅使用单一信号：

```typescript
// 单信号：TIP.z - DIP.z
const tipDipDiff = TIP.z - DIP.z;
if (tipDipDiff > NAIL_PALM_Z_THRESHOLD) return false;
return true;
```

### 1.2 三个问题

1. **z 坐标精度不足**：MediaPipe z 是单目视觉的相对深度估计，帧间噪声大，阈值 0.002 在实际使用中不可靠
2. **单信号脆弱**：z 差受手指长度／弯曲程度／手部距离影响，无冗余校验
3. **无帧间平滑**：每帧独立判定，抖动导致指甲闪烁（render↔skip 跳变）

### 1.3 目标状态

```
手背正对镜头 → 五指全部贴图 ✅
手心正对镜头 → 五指全部不贴 ✅（由全局门控处理）
手偏转 45°   → 部分指贴图，部分不贴 ⚠️（当前不可靠，需增强）
```

### 1.4 设计原则

- **保守（手心优先）**: 宁可漏判一根可见指甲，也不在手心侧误贴
- **独立判定**: 每根手指独立检测，支持混合态（3 指贴 + 2 指不贴）
- **平滑过渡**: 翻手过程中无闪烁跳变

---

## 2. 技术方案：三信号融合 + 时序平滑

### 2.1 三信号设计

#### 信号 A：指尖-关节 z 差（改进现有）

```
zdiff = TIP.z - DIP.z
visible = (zdiff <= NAIL_PALM_Z_THRESHOLD)   // 阈值 = 0.002
```

- 物理含义：TIP 比 DIP 更靠近镜头 → 指甲可能可见
- 使用平滑后的 z 值（减少噪声）
- 保持现有阈值 0.002

#### 信号 B：指尖-近端关节 z 差（新增，印证信号 A）

```
zdiff = TIP.z - PIP.z
visible = (zdiff <= NAIL_PALM_Z_THRESHOLD * 1.5)  // 阈值 = 0.003，更宽松
```

- 物理含义：PIP 比 DIP 更稳定（靠近指根，受弯曲影响小）
- 阈值更宽松（0.003 vs 0.002），作为 A 的印证信号
- A 和 B 使用不同的关节参考点，相关性可控

#### 信号 C：透视缩短比（新增，基于 x/y 几何）

```
dx = TIP.x - PIP.x
dy = TIP.y - PIP.y
dz = TIP.z - PIP.z

len2D = sqrt(dx² + dy²)          // 屏幕上投影长度
len3D = sqrt(dx² + dy² + dz²)    // 3D 空间长度

ratio = len2D / len3D             // 透视缩短比

visible = (ratio > FORESHORTEN_THRESHOLD)  // 阈值 = 0.65
```

**物理原理**：
- 手背朝镜头 → 手指与镜头平面平行 → 2D 投影 ≈ 3D 长度 → ratio ≈ 0.9~1.0
- 手偏转 45° → 手指斜向镜头 → ratio ≈ 0.7
- 手心朝镜头 → 手指指向镜头 → ratio < 0.5（严重缩短）

**优势**：主要依赖 x/y（MediaPipe 精度最高），z 只作为 3D 长度归一化的微小修正。

### 2.2 投票融合策略

```typescript
votes = [sigA, sigB, sigC].filter(Boolean).length

// 强否定（避免误判）：
if (!sigA && !sigC) return false    // z 差 + 几何都否定 → 手掌侧

// 多数投票：
return votes >= 2                    // ≥ 2 信号认可 → 可见
```

各信号独立性与互补性：

| 场景 | sigA (tip-dip z) | sigB (tip-pip z) | sigC (缩短比) | 投票 |
|------|:---:|:---:|:---:|:----:|
| 手背，五指清晰 | ✅ | ✅ | ✅ | 3 ✅ |
| 刚翻过手（过渡态） | ❌ | ✅ | ✅ | 2 ✅ |
| 手心明显 | ❌ | ❌ | ❌ | 0 ❌ |
| 侧手 90° | ✅ | ✅ | ❌ | 2 ✅ |
| 拇指特殊（弯曲） | ❌ | ✅ | ❌ | 1（保守：不渲染） |

### 2.3 时序平滑（防闪烁）

```
visibleRaw = computeFingerVisibility(...)     // 当前帧原始判定 (0/1)
visibleSmooth[f] = EMA(visibleSmooth[f], visibleRaw, ALPHA = 0.3)

if (visibleSmooth[f] < 0.5) → skip this finger
```

- 仍使用 `boolean[]` 作为状态，但用 EMA 平滑过渡
- 阈值 0.5：连续约 2 帧判定为 visible 后才真正渲染
- 同样需要约 2 帧持续判定为 hidden 后才停止渲染
- 有效消除单帧噪声导致的闪烁

### 2.4 与全局门控的关系

```
onResults 回调:
  1. shouldRenderNails()          ← 4 传感器融合（全部手心 → 阻止全部）
     └─ decision.render = false → 跳过整帧（手心：无需逐指判定）
     └─ decision.render = true  → 进入 paintNails
  
  2. paintNails() 内逐指判定
     ├─ EMA 平滑 tip/dip/pip
     ├─ computeFingerVisibility() ← 三信号融合（混合态：逐指过滤）
     ├─ 时序平滑 visibleSmooth[f]
     └─ 可见则贴图，不可见则 continue
```

**两层防御分工明确**：
- 全局层：整体手心 → 整帧跳过（节省 GPU，防止误判）
- 逐指层：非整体手心 → 逐指三信号融合（精确到单指）

---

## 3. 参数表

| 参数 | 值 | 信号 | 说明 |
|------|:---:|:------|------|
| `NAIL_PALM_Z_THRESHOLD` | 0.002 | A, B | TIP.z - DIP.z > 此值 → 手心侧 |
| `NAIL_PALM_Z_THRESHOLD_B` | 0.003 | B | TIP.z - PIP.z > 此值 → 手心侧（更宽松） |
| `FORESHORTEN_THRESHOLD` | 0.65 | C | len2D/len3D < 此值 → 透视缩短 → 手心侧 |
| `VISIBILITY_EMA_ALPHA` | 0.3 | 平滑 | 可见性状态帧间平滑 |
| `VISIBILITY_SMOOTH_THRESHOLD` | 0.5 | 平滑 | 连续判定阈值（≈ 2 帧确认） |

---

## 4. 验收标准

### A. 功能验收（需 PC/手机摄像头实测）

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 手背五指均贴图 | 手背正对摄像头，五指张开 | 五指甲位显示美甲，无缺失 |
| A2 | 手心五指均不贴 | 翻掌手心朝镜头，五指张开 | 五指均不显示美甲 |
| A3 | 手偏转混合态 | 从手背缓慢翻转到手心 | 部分手指先消失，逐步全部消失，无闪烁 |
| A4 | 拇指独立判定 | 手偏转时拇指先翻过来 | 拇指先消失，其他指仍贴图 |
| A5 | 食指+中指可见，其他隐藏 | 特殊偏转角度 | 仅可见的 2 指贴图 |
| A6 | 侧手全部可见 | 手掌垂直镜头 | 五指均贴图 |

### B. 代码验收（无需摄像头）

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint | `npx eslint .` | 0 errors（预存问题除外） |
| B3 | 三信号独立且互补 | 代码审查 | sigA/B 用不同关节，sigC 用几何 |
| B4 | 时序平滑存在 | 代码审查 | visibleSmoothRef + EMA |
| B5 | 全局门控保留 | 代码审查 | `if (decision.render)` 仍在 |

### C. 回归验收

| # | 验收项 | 预期结果 |
|---|--------|----------|
| C1 | `npm run build` | 通过，0 错误 |
| C2 | 编辑器 | 上传 → 涂抹 → 撤销 → 保存 正常 |
| C3 | 首页 | 光标交互正常 |
| C4 | AR 纯色/纹理切换 | 模式切换正常 |

---

## 5. 回退方案

如果三信号融合导致 regression：
1. 恢复到简单 `isNailVisible()`：注释三信号代码，启用备用 `return tipDipDiff <= NAIL_PALM_Z_THRESHOLD`
2. 调优阈值：
   - `FORESHORTEN_THRESHOLD`: 0.65→0.55（更宽松，更多手指被判定 visible）
   - `NAIL_PALM_Z_THRESHOLD`: 0.002→0.003（更宽松）
3. 如果 sigC 本身不稳定（手部距离变化影响 3D 长度），可临时排除

---

## 6. 文件修改清单

| 文件 | 修改 |
|------|------|
| `src/components/ArView.tsx` | 新增常量 + `visibleSmoothRef` + 替换 `isNailVisible()` 为三信号融合 |
| `docs/technical-architecture.md` | 更新 §5.5 参数表 |
| `dev-log/2026-06-24.md` | 追加记录 |

---

## 7. 验收追踪

- [x] **B1**: TypeScript 编译 ✅ — `npm run build` 0 错误
- [x] **B2**: ESLint ✅ — ArView.tsx 0 errors（仅预存 warnings）
- [x] **B3**: 代码审查 ✅ — sigA(DIP z) / sigB(PIP z) / sigC(x/y 几何) 三信号独立互补
- [x] **B4**: 时序平滑 ✅ — `visibleSmoothRef` + EMA(α=0.3) + 阈值 0.5
- [x] **B5**: 全局门控保留 ✅ — `if (decision.render)` 在第 931 行
- [x] **C1**: 回归验收 ✅ — build 通过，所有路由编译正常
- [ ] **A1**: 手背五指贴图（需真机测试）
- [ ] **A2**: 手心五指不贴（需真机测试）
- [ ] **A3**: 偏转混合态无闪烁（需真机测试）
- [ ] **A4**: 拇指独立判定（需真机测试）
- [ ] **A5**: 局部手指可见（需真机测试）
- [ ] A3: 偏转混合态无闪烁
- [ ] A4: 拇指独立判定
- [ ] A5: 局部手指可见
