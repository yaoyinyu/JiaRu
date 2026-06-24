# 反转手按钮朝向检测修正 — 有效 handedness 分层使用

**创建时间**: 2026-06-24
**修复目标**: 反转手按钮只影响 UI 显示，不影响手心/手背朝向判定
**对应文件**: `src/components/ArView.tsx`

---

## 1. 问题分析

### 1.1 当前代码的错误

反转按钮工作后，`effectiveHandedness` 被用于**两处**：

```typescript
// ① UI 显示 ← 应该使用有效值
setHandLabel(effectiveHandedness === "Right" ? "右手" : ...);

// ② 朝向检测 ← ❌ 不应该使用有效值！
const decision = shouldRenderNails(lm, smoothDepthDiff, effectiveHandedness);
```

### 1.2 为什么朝向检测必须用原始 handedness

`shouldRenderNails()` 中的两个传感器依赖 handedness 符号：

**方案 A（叉积法向量）**：基于 `lm[5]-lm[0]` 和 `lm[17]-lm[0]` 在图像平面上的排列方向
```
右手手背 → 三角形顺时针 → crossZ < 0
左手手背 → 三角形逆时针 → crossZ > 0
```
反转 handedness 会错误地解释这个几何方向。

**方案 D（拇指位置）**：拇指在大拇指侧，左右手位置相反
```
右手手背 → 拇指在画面右侧（thumbOffsetX > 0）
左手手背 → 拇指在画面左侧（thumbOffsetX < 0）
```
反转 handedness 会导致拇指位置的判定符号错误。

### 1.3 场景追踪

| 场景 | rawHandedness | effectiveHandedness | shouldRenderNails 用哪个？ | UI 显示 |
|------|:-------------:|:-------------------:|:------------------------:|:-------:|
| 正常 + 右手 | Right | Right | ✅ Right → 手背 | ✅ 右手 |
| 镜像 + 右手 | Left | Left（未反转） | ✅ Left → 手背（画面几何 = 左手） | ❌ 左手 |
| 镜像 + 右手 + 按反转 | Left | Right | ❌ Right → 手心（bug！） | ✅ 右手 |
| **修正后**: 镜像 + 右手 + 按反转 | Left | Right | ✅ **Left** → 手背 | ✅ **右手** |

### 1.4 设计原则

- **朝向检测绑定画面几何**：`shouldRenderNails()` 始终使用 rawHandedness（匹配 MediaPipe 看到的实际 x/y 几何排列）
- **用户标签绑定实际手**：`setHandLabel()` 使用 effectiveHandedness（用户知道自己用的哪只手）

---

## 2. 修改方案

### 2.1 代码变更

```typescript
// 朝向检测 — 用原始 handedness（画面几何）
const decision = shouldRenderNails(lm, smoothDepthDiff, rawHandedness);

// UI 显示 — 用有效 handedness（用户实际手）
setHandLabel(effectiveHandedness === "Right" ? "右手" : ...);
```

### 2.2 效果

```
反转按钮 → 只翻转 UI 标签
         → 不传给 shouldRenderNails
         → 朝向判定不变
         → 贴图行为不变
```

### 2.3 与现有架构的关系

```
onResults:
  ├── rawHandedness              ← MediaPipe 原始输出
  ├── effectiveHandedness        ← 仅用于 setHandLabel()
  ├── shouldRenderNails(rawHandedness)  ← 朝向检测（不反转）
  │
  ├── setHandLabel(effectiveHandedness) ← UI 显示（反转）
  └── paintNails()               ← 不受影响
```

---

## 3. 验收标准

### A. 功能验收

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 反转后手背识别正确 | 右手手背 → 按反转按钮 | 显示「右手 · 手背」，五指贴图 |
| A2 | 反转后手心识别正确 | 翻到手心 | 显示「右手 · 手心」，五指不贴图 |
| A3 | 反转前后朝向一致 | 不按/按下反转，保持手背 | 两次都显示「手背」，贴图一致 |
| A4 | 不反转时功能不变 | 右手手背，不按按钮 | 显示「右手 · 手背」，贴图正常 |
| A5 | 画面不受影响 | 反转前后 | 视频镜像不变 |

### B. 代码验收

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint | `npx eslint .` | 0 errors |
| B3 | `shouldRenderNails` 使用 rawHandedness | 代码审查 | 参数传 rawHandedness |
| B4 | `setHandLabel` 使用 effectiveHandedness | 代码审查 | 参数传 effectiveHandedness |
| B5 | 灵敏度不变 | 代码审查 | 阈值、融合逻辑、投票机制均不修改 |

### C. 回归验收

| # | 验收项 | 预期结果 |
|---|--------|----------|
| C1 | `npm run build` | 通过 |
| C2 | 不按反转时与之前完全一致 | 朝向、贴图、检测全部不变 |
| C3 | 反转后贴图不反 | 五指贴图/不贴图状态与反转前相同 |

---

## 4. 回退方案

如果修改后仍有问题，直接撤销本变更：`git revert HEAD`（单 commit，可安全回退）。

---

## 5. 验收追踪

- [x] **B1**: TypeScript 编译 ✅ — `npm run build` 0 错误
- [x] **B2**: ESLint ✅ — ArView.tsx 0 errors
- [x] **B3**: shouldRenderNails 用 rawHandedness ✅ — `shouldRenderNails(lm, depth, rawHandedness)`
- [x] **B4**: setHandLabel 用 effectiveHandedness ✅ — `setHandLabel(effectiveHandedness...)`
- [x] **B5**: 灵敏度不修改 ✅ — 阈值、融合逻辑、投票均未修改
- [x] **C1**: 回归验收 ✅ — build 通过
- [ ] **A1/A2/A3**: 反转后朝向正确（需真机测试）
- [ ] **A4**: 不反转时功能不变（需真机测试）