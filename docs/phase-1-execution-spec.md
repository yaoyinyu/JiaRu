# 甲如 (JiaRu) 阶段一技术执行文档

**生成时间**：2026-06-23 01:05 CST
**执行人**：QClaw
**项目路径**：`E:\AI Project\ClaudeCode\JiaRu`

---

## 一、技术验证结果

### 1.1 构建验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `npm run build` | ✅ 通过 | Next.js 16.2.9 (Turbopack) 编译成功，7 个路由全部静态生成 |
| TypeScript 编译 | ✅ 通过 | `Finished TypeScript in 1442ms`，0 类型错误 |
| ESLint 检查 | ❌ 39 个问题 | 30 errors + 9 warnings（详见下文） |

### 1.2 ESLint 问题完整清单

#### src/components/NailCanvas.tsx（8 errors, 2 warnings）

| 行号 | 严重度 | 规则 | 问题 |
|------|--------|------|------|
| 42 | error | react-hooks/immutability | `saveHistory` 在声明前被访问（useEffect 内调用） |
| 48 | error | react-hooks/preserve-manual-memoization | `useCallback` 无法被 React Compiler 保留 |
| 103 | error | react-hooks/immutability | `let lastPos` 是局部变量，渲染后被重新赋值 |
| 110 | error | react-hooks/immutability | `lastPos = pos` 在事件处理器中赋值局部变量 |
| 122 | error | react-hooks/immutability | `lastPos = pos` 同上 |
| 128 | error | react-hooks/immutability | `lastPos = null` 同上 |
| 170 | error | react-hooks/immutability | `onMouseDown={handleStart}` 该函数可能修改 lastPos |
| 171 | error | react-hooks/immutability | `onMouseMove={handleMove}` 同上 |
| 45 | warning | react-hooks/exhaustive-deps | useEffect 缺少依赖 `saveHistory` |
| 172 | error | react-hooks/immutability | `onMouseUp={handleEnd}` 该函数可能修改 lastPos |

**根因**：`lastPos` 应使用 `useRef` 而非局部 `let` 变量；`saveHistory` 应在 useEffect 内定义或使用 ref。

#### src/components/ArView.tsx（9 errors, 2 warnings）

| 行号 | 严重度 | 规则 | 问题 |
|------|--------|------|------|
| 11 | error | react-hooks/refs | `colRef.current = nailColors` 在渲染期间更新 ref |
| 23 | error | prefer-const | `rafId` 声明为 let 但从未重新赋值 |
| 24 | error | @typescript-eslint/no-explicit-any | `handsInst: any` |
| 24 | error | prefer-const | `streamInst` 声明为 let 但从未重新赋值 |
| 24 | warning | @typescript-eslint/no-unused-vars | `streamInst` 赋值后从未使用 |
| 55 | error | @typescript-eslint/no-explicit-any | `(window as any).Hands` |
| 56 | error | @typescript-eslint/no-explicit-any | `(window as any).Camera` |
| 81 | error | @typescript-eslint/no-explicit-any | `res: any` onResults 回调 |
| 92 | error | @typescript-eslint/no-explicit-any | `res: any` 同上 |
| 106 | error | react-hooks/immutability | `paintNails` 在声明前被访问 |
| 133 | warning | react-hooks/exhaustive-deps | useEffect 缺少依赖 `handCnt` |
| 135 | error | @typescript-eslint/no-explicit-any | `lm: any[]` paintNails 参数 |

**根因**：
- `colRef.current = nailColors` 应放在 useEffect 内
- `rafId` 和 `streamInst` 应改为 `const`（或移除未使用的 `streamInst`）
- MediaPipe 全局变量需要最小类型声明替代 `any`
- `paintNails` 应移到 useEffect 内或用 useCallback/ref

#### src/app/privacy/page.tsx（4 errors）

| 行号 | 严重度 | 规则 | 问题 |
|------|--------|------|------|
| 16 | error | react/no-unescaped-entities | `"甲如"` 中的引号未转义 |
| 16 | error | react/no-unescaped-entities | 同上（4 处引号） |

**根因**：JSX 文本中的 `"` 应改为 `&quot;` 或使用中文引号 `「」`。

#### src/app/editor/page.tsx（1 warning）

| 行号 | 严重度 | 规则 | 问题 |
|------|--------|------|------|
| 8 | warning | @typescript-eslint/no-unused-vars | `Link` 导入但未使用 |

#### src/app/ai-generate/page.tsx（1 warning）

| 行号 | 严重度 | 规则 | 问题 |
|------|--------|------|------|
| 78 | warning | @next/next/no-img-element | 使用 `<img>` 而非 `<Image />` |

#### src/app/ar-tryon/page.tsx（1 warning）

| 行号 | 严重度 | 规则 | 问题 |
|------|--------|------|------|
| 29 | warning | @typescript-eslint/no-unused-vars | `resetView` 定义但未使用 |

#### backup_ar_working/（同一文件重复，应排除）

- `backup_ar_working/ArView.tsx` 产生与 `src/components/ArView.tsx` 相同的 lint 错误
- **解决方案**：将 `backup_ar_working/` 添加到 `.gitignore` 或 eslint ignore

### 1.3 其他验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| .gitignore 包含 certificates/ | ❌ 缺失 | `Select-String "cert" → False` |
| Git 未提交变更 | 20 行 status | 7 修改 + 12 未跟踪 |
| SVG 占位图中文乱码 | ❌ | `placeholder-1.svg` 中 `娓愬彉瑁哥矇` 是乱码 |
| GalleryGrid 未使用 item.src | ❌ | 组件渲染 emoji 💅 而非图片 |
| 根目录无关图片 | 743KB | `1f65f04cdd5df509463a03fb17d8ea03.jpg` |
| ACP subagent 可用 | ❌ | 只有 main agent，无 Claude Code agent |

### 1.4 执行方式确认

ACP subagent 不可用，所有操作通过 QClaw 的 exec + edit 工具直接完成。

---

## 二、任务清单与验收标准

### Task 1: Git commit + .gitignore 修复

**目标**：保存当前所有代码到 git 历史，防止丢失。

**操作**：
1. `.gitignore` 添加：`certificates/`、`*.pem`、`backup_ar_working/`、`1f65f04cdd5df509463a03fb17d8ea03.jpg`
2. 删除根目录无关图片 `1f65f04cdd5df509463a03fb17d8ea03.jpg`
3. `git add -A && git commit -m "Phase 1 MVP + AR Step 1 + docs"`

**验收标准**：
- [ ] `git status` 显示 clean（无未提交变更）
- [ ] `git log` 至少 2 条 commit
- [ ] `.gitignore` 包含 `certificates/` 和 `*.pem`
- [ ] 根目录无 `1f65f04cdd5df509463a03fb17d8ea03.jpg`
- [ ] `backup_ar_working/` 不再被 git 跟踪

---

### Task 2: 修复 NailCanvas.tsx（10 个 lint 问题）

**目标**：修复所有 React Hooks 规则违规。

**具体修改**：

1. **`lastPos` 改为 `useRef`**
   - 删除 `let lastPos: Point | null = null;`
   - 添加 `const lastPosRef = useRef<Point | null>(null);`
   - 所有 `lastPos` → `lastPosRef.current`
   - `lastPos = pos` → `lastPosRef.current = pos`
   - `lastPos = null` → `lastPosRef.current = null`

2. **`saveHistory` 改为 `useRef`**
   - `useCallback` 改为 `useRef`，在 useEffect 内赋值
   - 或将 `saveHistory` 移入 useEffect 内部定义

3. **移除 `useCallback` 包裹**（React Compiler 无法保留）
   - `saveHistory` 改为普通函数定义在 useEffect 内

**验收标准**：
- [ ] `npx eslint src/components/NailCanvas.tsx` 输出 0 errors
- [ ] `npm run build` 通过
- [ ] 编辑器功能不变：上传照片 → 涂色 → 撤销 → 重置 → 保存

---

### Task 3: 修复 ArView.tsx（9 errors, 2 warnings）

**目标**：修复所有 React Hooks + TypeScript 规则违规。

**具体修改**：

1. **`colRef.current = nailColors` 移入 useEffect**
   - 删除第 11 行
   - 在 useEffect 开头添加 `colRef.current = nailColors;`

2. **`let rafId` → `const rafId`**
   - 第 23 行，从未重新赋值

3. **移除未使用的 `streamInst`**
   - 第 24 行，`streamInst` 赋值后从未使用

4. **MediaPipe 全局变量添加最小类型声明**
   ```typescript
   declare global {
     interface Window {
       Hands: new (config: { locateFile: (f: string) => string }) => {
         setOptions: (opts: Record<string, unknown>) => void;
         onResults: (cb: (res: HandResults) => void) => void;
         close: () => void;
         send: (data: { image: HTMLVideoElement }) => Promise<void>;
       };
       Camera: new (video: HTMLVideoElement, opts: {
         onFrame: () => Promise<void>;
         width: number; height: number; facingMode: string;
       }) => { start: () => void };
     }
   }
   interface HandResults {
     multiHandLandmarks: Array<Array<{ x: number; y: number; z: number }>>;
   }
   ```
   - 替换所有 `(window as any)` 为类型安全的 `window.Hands` / `window.Camera`
   - `res: any` → `res: HandResults`
   - `lm: any[]` → `lm: Array<{ x: number; y: number; z: number }>`

5. **`paintNails` 移到 useEffect 内部**
   - 消除 "accessed before declared" 错误
   - 或用 `useRef` 存储函数引用

6. **诊断面板加条件渲染**
   - `{status !== "ready" && (<div className="absolute top-1 ...">...</div>)}`

**验收标准**：
- [ ] `npx eslint src/components/ArView.tsx` 输出 0 errors
- [ ] `npm run build` 通过
- [ ] 诊断面板仅在非 ready 状态显示
- [ ] AR 组件结构不变：摄像头 → MediaPipe → 指甲绘制

---

### Task 4: 修复其他 lint 问题（6 个文件）

**目标**：清除所有剩余 lint 错误和警告。

**具体修改**：

1. **`src/app/privacy/page.tsx`**
   - 第 16 行：`"甲如"` → `「甲如」`
   - `"本地优先"` → `「本地优先」`

2. **`src/app/editor/page.tsx`**
   - 删除 `import Link from "next/link";`（第 8 行，未使用）

3. **`src/app/ai-generate/page.tsx`**
   - `<img>` → `<Image />`（import next/image）
   - 或在 eslint.config.mjs 中对该规则添加 disable 注释（Phase 2 会重写）

4. **`src/app/ar-tryon/page.tsx`**
   - 移除未使用的 `resetView` 函数（第 29-32 行）

5. **eslint.config.mjs 添加 ignore**
   - 添加 `backup_ar_working/` 到 eslint ignore

**验收标准**：
- [ ] `npx eslint .` 输出 0 errors（warnings 可接受）
- [ ] `npm run build` 通过

---

### Task 5: 图库 SVG 修复

**目标**：修复占位 SVG 的中文乱码问题，使图库组件实际使用 SVG 文件。

**具体修改**：

1. **重写 6 个 SVG 文件**
   - 修复中文文字编码（使用 UTF-8 正确编码）
   - 每个 SVG 展示不同美甲款式（渐变裸粉、法式白边、亮片闪粉、简约纯色、复古花纹、宝石镶嵌）
   - 尺寸 400×400，品牌色系

2. **修改 GalleryGrid.tsx 使用 item.src**
   - 当前：`<span className="text-4xl">💅</span>`
   - 改为：`<img src={item.src} alt={item.name} />`（或 `<Image />`）

**验收标准**：
- [ ] 6 个 SVG 文件中文文字正常显示
- [ ] GalleryGrid 渲染图片而非 emoji
- [ ] `npm run build` 通过
- [ ] 图库页面显示 6 个不同款式的美甲图片

---

### Task 6: 编辑器五指独立选色

**目标**：编辑器支持每根手指不同颜色（法式美甲、渐变款需求）。

**具体修改**：

1. **`src/lib/utils.ts`**
   - 添加 `FINGER_NAMES` 常量（复用 AR 模块的定义）

2. **`src/components/NailCanvas.tsx`**
   - Props 接口：`selectedColor: string` → `nailColors: string[]` + `activeFinger: number`
   - `drawDot` 使用 `nailColors[activeFinger]` 替代 `selectedColor`
   - `Point` 接口的 `color` 字段保持（内部使用）

3. **`src/app/editor/page.tsx`**
   - 添加 `nailColors` state（5 个颜色，默认全 `#E8A0BF`）
   - 添加 `activeFinger` state（默认 0）
   - 添加手指选择 tab UI（复用 AR 页面的布局）
   - 添加"应用到全部"按钮
   - `ColorPalette` 选色时更新 `nailColors[activeFinger]`

**验收标准**：
- [ ] 编辑器顶部显示 5 个手指选择按钮
- [ ] 选择手指后，颜色面板更新为该手指当前颜色
- [ ] 涂抹时使用当前选中手指的颜色
- [ ] "应用到全部"按钮将当前手指颜色应用到所有 5 个手指
- [ ] 撤销/重置/保存功能不受影响
- [ ] `npx eslint src/app/editor/page.tsx src/components/NailCanvas.tsx` 0 errors
- [ ] `npm run build` 通过

---

### Task 7: 生产构建验证 + 部署准备

**目标**：确保项目可以部署到 Vercel。

**操作**：
1. `npm run build` 最终验证
2. `npx eslint .` 最终验证
3. 检查 `next.config.ts` 配置是否适合 Vercel
4. 生成部署清单文档

**验收标准**：
- [ ] `npm run build` 成功，0 错误
- [ ] `npx eslint .` 0 errors（warnings ≤ 3 个）
- [ ] `next.config.ts` 无硬编码 IP（`allowedDevOrigins` 可移除或改为通配）
- [ ] 部署清单文档已生成

---

## 三、执行顺序

```
Task 1 (Git commit)          ← 保命，第一优先
  ↓
Task 2 (NailCanvas fix)      ← 独立，不依赖其他
  ↓
Task 3 (ArView fix)           ← 独立，不依赖其他
  ↓
Task 4 (其他 lint fix)        ← 依赖 Task 2/3 完成（避免冲突）
  ↓
Task 5 (图库 SVG)             ← 独立
  ↓
Task 6 (五指选色)             ← 依赖 Task 2（NailCanvas 接口变更）
  ↓
Task 7 (构建验证)             ← 依赖所有 Task 完成
```

每个 Task 完成后：
1. 运行验收命令
2. 在本文档对应位置标记 `[x]`
3. 如果验收失败，修复后重新验收
4. 验收通过后才进入下一个 Task

---

## 四、风险与回退

| 风险 | 概率 | 回退方案 |
|------|------|----------|
| NailCanvas 重构引入功能 regression | 中 | git stash + 恢复原版 |
| ArView 类型声明不兼容 MediaPipe 运行时 | 低 | 回退到 `any` + eslint-disable |
| 五指选色改动范围扩大 | 中 | 仅改 NailCanvas 接口，保持编辑器逻辑最小变更 |
| build 失败 | 低 | 逐步修改，每步 build 验证 |

---

## 五、验收追踪

### Task 1: Git commit + .gitignore 修复
- [ ] `git status` clean
- [ ] `git log` ≥ 2 commits
- [ ] `.gitignore` 含 `certificates/` + `*.pem`
- [ ] 根目录无无关图片
- [ ] `backup_ar_working/` 被 git ignore

### Task 2: NailCanvas.tsx 修复
- [ ] eslint 0 errors
- [ ] build 通过
- [ ] 编辑器功能正常

### Task 3: ArView.tsx 修复
- [ ] eslint 0 errors
- [ ] build 通过
- [ ] 诊断面板条件渲染

### Task 4: 其他 lint 修复
- [ ] eslint 全局 0 errors
- [ ] build 通过

### Task 5: 图库 SVG 修复
- [ ] SVG 中文正常
- [ ] GalleryGrid 渲染图片
- [ ] build 通过

### Task 6: 编辑器五指选色
- [ ] 手指选择 UI
- [ ] 颜色面板联动
- [ ] 撤销/重置/保存正常
- [ ] eslint + build 通过

### Task 7: 构建验证 + 部署准备
- [ ] build 0 错误
- [ ] eslint 0 errors
- [ ] 部署清单生成
