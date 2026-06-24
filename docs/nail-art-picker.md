# 美甲纹理提取与按指分配 — 技术方案

**创建时间**: 2026-06-24
**目标**: 用户上传美甲参考图 → 识别图中各指甲区域 → 用户选择款式并分配到手 → AR 贴合
**涉及文件**: 新增 `src/components/NailArtPicker.tsx` + 修改 `src/app/ar-tryon/page.tsx`

---

## 1. 需求分析

### 1.1 用户旅程

```
用户打开 AR 页 → 上传美甲参考图（如手部展示多种美甲款式的照片）
  → 系统展示图片并高亮识别到的各指甲区域
  → 用户点选其中一款美甲 → 选择应用到手部哪根手指（拇指/食指/中指/无名指/小指）
  → 可重复操作：为每根手指分配不同的美甲纹理
  → 切换到 AR 摄像头 → 美甲纹理实时贴合到用户对应的手指上
```

### 1.2 关键场景

| 场景 | 参考图内容 | 用户操作 | 预期结果 |
|------|-----------|----------|----------|
| 单色统一款 | 五指都是同款美甲 | 选一次→应用到全部 | 五指同一纹理 |
| 跳色款 | 拇指+无名指红色，其余白色 | 选红色→分配到拇指/无名指；选白色→分配到其余指 | 五指按指定颜色渲染 |
| 法式款 | 五指法式白边 | 在每个指甲上框选 | 纹理按照指甲形状贴合 |
| 复杂图案 | 仅展示一个美甲 | 选该指甲→分配到五根手指 | 五指统一为该图案 |

### 1.3 与现有功能的区别

| 功能 | 现有 TextureCropper | 新增 NailArtPicker |
|------|--------------------|--------------------|
| 选区形状 | 矩形 | ★ 贝塞尔指甲形状 |
| 选区数量 | 单个 | ★ 多个（每指一个） |
| 提取目标 | 一个纹理 | ★ 多个纹理 + 指纹分配 |
| 结果输出 | `ImageBitmap` | ★ `{texture, targetFinger}[]` |

---

## 2. 技术方案

### 2.1 架构图

```
ar-tryon/page.tsx
│
├── 现有: TextureCropper (矩形裁剪，单纹理)
│   └── handleCropConfirm(bitmap) → nailTextures[activeFinger]
│
└── ★ 新增: NailArtPicker (指甲形状选区，多纹理 + 指纹分配)
    └── handlePickingConfirm(assignments[]) → nailTextures[assignment.finger]
                                                          ↑
    每个 assignment = { texture: ImageBitmap, finger: 0-4 }
```

### 2.2 组件 NailArtPicker

```
Props:
  imageUrl: string — 上传的参考图 URL
  onConfirm: (assignments: NailAssignment[]) => void
  onCancel: () => void

State:
  regions: NailRegion[]       ← 用户添加的选区列表
  selectedIdx: number | null  ← 当前选中的选区
  mode: "add" | "adjust"     ← 添加模式 / 调整模式

NailRegion:
  id: string
  cx: number, cy: number      ← 中心位置 (归一化 0-1)
  angle: number               ← 旋转角 (弧度)
  nailLength: number          ← 指甲长度 (像素)
  nailWidth: number           ← 指甲宽度 (像素)
  assignedFinger: number|null ← 目标手指 0-4

NailAssignment:
  texture: ImageBitmap        ← 提取的纹理
  finger: number              ← 目标手指 0-4

UI 结构:
┌──────────────────────────┐
│  顶部提示栏               │
│  [添加选区] [完成分配]    │
├──────────────────────────┤
│                          │
│   参考图 + 选区覆盖层     │
│   ┌─ 贝塞尔指甲形状 ──┐  │
│   │  (可拖拽/缩放/旋转) │  │
│   └───────────────────┘  │
│   ┌─ 贝塞尔形状 2 ────┐  │
│   └───────────────────┘  │
│                          │
├──────────────────────────┤
│  当前选区: 第 1 个/共 3 个│
│  分配到手: [拇][食][中]  │
│         [无][小]         │
│  [删除选区] [调整位置]   │
└──────────────────────────┘
```

### 2.3 选区交互方式

**添加选区**: 用户点击"添加选区"按钮 → 在图片中央出现一个默认大小的指甲形状 → 拖拽到对应指甲位置

**调整位置**: 拖拽指甲形状的中心点

**调整大小**: 
- 长度控制: 拖拽指尖端的控制点
- 宽度控制: 拖拽侧边的控制点

**调整旋转**: 使用滑块或两点拖拽旋转

**选择选区**: 点击已有的选区（获取焦点，显示控制手柄）

**删除选区**: 选中后点击删除按钮

**分配手指**: 选中后点击底部手指按钮

### 2.4 贝塞尔指甲形状选区

使用与 `drawNailShape()` 相同的贝塞尔路径，但是在选择模式下：
- 透明填充 + 粉色边框 + 控制手柄
- 选中态：实线 + 发光
- 未选中态：虚线

### 2.5 纹理提取流程

```
用户调整完选区位置/大小/旋转 → 点击"确认"按钮
  → 对每个 NailRegion:
    1. 在离屏 canvas 上裁取选区区域（考虑旋转）
    2. 应用柱面曲率变形（匹配 AR 渲染效果）
    3. 调用 extractTexture() → ImageBitmap
  → 返回 NailAssignment[] 给父组件
  → 父组件更新 nailTextures[assignment.finger] = assignment.texture
```

### 2.6 与 AR 渲染的衔接

```
NailArtPicker 返回后:
  ar-tryon 的 handlePickingConfirm() 被调用
  → 遍历 assignments[]
  → 对每个 assignment:
     如果 nailTextures[assignment.finger] 已有值 → 释放旧纹理
     nailTextures[assignment.finger] = assignment.texture
  → setMode("texture") 自动切换到纹理模式
  → 用户切换到 AR 摄像头 → 美甲在对应手指上渲染
```

### 2.7 集成路径

当前 ar-tryon 的纹理上传流程：

```
上传图片 → showCropper=true → TextureCropper
  → onConfirm(bitmap) → nailTextures[activeFinger] = bitmap → setMode("texture")
```

新增路径：

```
上传图片 → showCropper=true → ★NailArtPicker (指甲选区)
  → onConfirm(assignments[]) → 遍历赋值 nailTextures[assignment.finger] → setMode("texture")
```

同时保留 TextureCropper 作为"快速单纹理"入口。

---

## 3. 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/components/NailArtPicker.tsx` | 新增 | 核心组件：多指甲选区 + 分配 UI |
| `src/app/ar-tryon/page.tsx` | 修改 | 集成 NailArtPicker，新增 handlePickingConfirm |
| `docs/technical-architecture.md` | 更新 | 新增提取 + 分配流程 |

---

## 4. 验收标准

### A. 功能验收

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| A1 | 上传参考图 | 上传含多款美甲的手部照片 | 显示参考图，可添加指甲选区 |
| A2 | 添加选区 | 点击"添加选区"，拖拽到指甲位置 | 指甲形状覆盖在指甲上 |
| A3 | 调整选区 | 拖拽/缩放/旋转选区 | 选区贴合指甲边界 |
| A4 | 多选区 | 添加 2-3 个选区 | 每个选区独立，可分别选中 |
| A5 | 分配手指 | 选中选区 → 点击"食指"按钮 | 选区显示「食」标记 |
| A6 | 不同指不同纹理 | 选区1→食指，选区2→无名指 | 两指分配不同纹理 |
| A7 | 确认提取 | 点击"完成分配" | 对应手指的 AR 纹理更新 |
| A8 | AR 贴合 | 切换到摄像头 | 食指和无名指纹贴显示正确纹理 |
| A9 | 应用到全部 | 选中一个选区→"应用到全部手指" | 五指纹贴统一 |

### B. 代码验收

| # | 验收项 | 方法 | 预期结果 |
|---|--------|------|----------|
| B1 | TypeScript 编译 | `npm run build` | 0 错误 |
| B2 | ESLint | `npx eslint .` | 0 errors |
| B3 | 贝塞尔选区渲染 | 代码审查 | 使用与 drawNailShape 相同的贝塞尔曲线 |
| B4 | 选区交互 | 代码审查 | 拖拽/缩放/旋转实现正确 |
| B5 | 纹理提取 | 代码审查 | extractTexture 调用正确 |
| B6 | 分配映射 | 代码审查 | assignments → nailTextures 映射正确 |
| B7 | 内存管理 | 代码审查 | 释放旧纹理时引用计数正确 |

---

## 5. 风险与回退

| 风险 | 概率 | 缓解 |
|------|:----:|------|
| 贝塞尔选区交互复杂实现时间长 | 中 | 优先实现核心功能（添加/拖拽/分配），缩放旋转可以简化 |
| 选区旋转后纹理提取偏移 | 低 | 使用 canvas 变换矩阵精确控制 |
| 现有 TextureCropper 被完全替代 | 低 | 保留 TextureCropper 作为快速入口 |

---

## 6. 验收追踪

- [ ] B1: TypeScript 编译
- [ ] B2: ESLint
- [ ] A1: 参考图显示
- [ ] A2: 选区添加
- [ ] A5: 手指分配
- [ ] A7: 纹理提取
- [ ] A8: AR 贴合
