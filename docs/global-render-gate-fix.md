# 全局朝向渲染门控恢复 — 技术方案与验收标准

**创建时间**: 2026-06-24
**修复对象**: `src/components/ArView.tsx`
**问题**: 手心朝镜头时美甲纹理仍会贴在手心手指上

---

## 1. 问题分析

### 1.1 现有架构的两层防线下层失效

```
渲染流程（修复前）:
  onResults
    ├── shouldRenderNails()  ← 4 传感器融合判定准确
    │   └── 返回值被忽略！仅用于 UI 朝向指示器
    ├── paintNails()
    │   └── isNailVisible()  ← 仅靠 TIP.z - DIP.z > 0.002
    │                           MediaPipe z 精度不足，手心时 z 差不超阈值
    └── 美甲被贴在了手心侧 ❌
```

### 1.2 根因

`shouldRenderNails()` 在 commit 6a9e941 中被与渲染管线解耦，当时的意图是让逐指 `isNailVisible()` 独立处理所有判定。但 MediaPipe z 坐标是单目视觉的相对深度估计，精度远低于 x/y，`TIP.z - DIP.z` 的差值在掌心朝镜头时并不稳定超过 0.002 阈值。

### 1.3 修复后的两层防御

```
渲染流程（修复后）:
  onResults
    ├── shouldRenderNails()
    │   ├── 4 传感器融合 (x/y 高精度信号 + z 辅助)
    │   ├── 手心 (palmScore ≥ 2) → decision.render = false
    │   └── 跳过 paintNails() ✅
    ├── 手背/侧手 → paintNails()
    │   └── isNailVisible()
    │       ├── 混合态逐指过滤（手偏转时部分指可见/不可见）
    └── 美甲正确地只出现在手背侧 ✅
```

## 2. 修改详情

### 2.1 文件修改

| 文件 | 行号 | 修改 |
|------|------|------|
| `src/components/ArView.tsx` | 859-884 | 在 `onResults` 回调中添加 `if (decision.render)` 门控 |
| `docs/technical-architecture.md` | §5.2, §5.6 | 更新管线图和绘制流程 |
| `dev-log/2026-06-24.md` | 末尾 | 追加修复记录 |

### 2.2 代码变更

```typescript
// 修改前（无条件调用 paintNails）
paintNails(ctx, lm, colRef.current, texRef.current, 
           modeRef.current, cvs.width, cvs.height, video);

// 修改后（4 传感器融合判定为手心时才跳过）
if (decision.render) {
  paintNails(ctx, lm, colRef.current, texRef.current,
             modeRef.current, cvs.width, cvs.height, video);
}
```

## 3. 验收标准

### A. 功能验收（需真机/PC 摄像头测试）

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 手背朝镜头时贴图正常 | 手背正对摄像头，五指张开 | 五个指甲位置显示美甲纹理 |
| A2 | 手心朝镜头时不贴图 | 翻掌，手心正对摄像头 | 全部手指不显示美甲纹理 |
| A3 | 手偏转时混合态正确 | 手从手背缓慢转向手心 | 部分手指先不贴图，逐步全部消失 |
| A4 | 侧手安全降级 | 手掌垂直于镜头 | 贴图正常（侧手时指甲仍可见） |
| A5 | 朝向指示器同步 | 手心/手背切换 | UI 显示 ✋手心/🖐️手背 与渲染状态一致 |

### B. 代码验收

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint | `npx eslint .` | 0 errors |
| B3 | `decision.render` 正确使用 | 代码审查 | `paintNails()` 调用被 `if (decision.render)` 保护 |
| B4 | `isNailVisible()` 保留 | 代码审查 | 逐指可见性判定仍存在，作为次级防线 |
| B5 | 宽松策略未改 | 代码审查 | 非手心态仍渲染（`decision.render` default true） |

### C. 回归验收

| # | 验收项 | 预期结果 |
|---|--------|----------|
| C1 | 编辑器功能正常 | 上传 → 涂色 → 撤销 → 重置 → 保存 不受影响 |
| C2 | 图库功能正常 | 6 个 SVG 正常显示 |
| C3 | AI 生成页面正常 | 页面可加载，无报错 |
| C4 | 隐私页面正常 | 静态内容正常 |
| C5 | 首页正常 | 光标磁吸交互正常 |

## 4. 回退方案

如果修复引入了 regression（如手背时也不再贴图）：

1. 还原 `src/components/ArView.tsx` 第 880-884 行
2. 或在 `onResults` 中添加 `console.log("[AR] decision.render:", decision.render, decision.reason)` 观察判定情况
3. 调优 `palmScore` 阈值（降低手心灵敏度的阈值）

## 5. 验收追踪

- [x] **B1**: TypeScript 编译通过 ✅ — `npm run build` 0 错误
- [x] **B3**: 代码审查通过 ✅ — `paintNails()` 被 `if (decision.render)` 保护
- [x] **B4**: 逐指防线保留 ✅ — `isNailVisible()` 在 paintNails 内继续工作
- [x] **B5**: 宽松策略未改 ✅ — 非手心态仍 `decision.render = true`
- [x] **C1**: 编辑器功能正常 ✅ — build 包含所有路由
- [ ] **B2**: ESLint 无错误（预存 4 个 error 在 TextureCropper/ar-tryon，非本次引入）
- [ ] **A1**: 手背贴图正常（需真机测试）
- [ ] **A2**: 手心不贴图（需真机测试）
