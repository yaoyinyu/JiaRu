# 前端交互成套修改方案

- 版本：2026-11-02
- 状态：**Batch 1—8 已实施（2026-11-03，白皮书 v1.2.213）**；浏览器关键路径手动验收与真机复核待执行
- 依据：白皮书 v1.2.208；`frontend-design` 与 `web-design-guidelines` 技能评审
- 范围：正式站首页、全局导航、`/gallery`、`/editor`、`/ai-generate`、`/ar-tryon`、`/nail-analysis`、`/login`、`/account`、`/privacy`
- 明确排除：独立设计预览 `127.0.0.1:4318`、正式识别模型训练与发布门、云端同步、商户/订单/支付、3D 指甲网格

---

## 1. 方案定位

### 1.1 总目标

把当前前端从“功能已打通、交互局部可用”提升为：

1. **可信**：不出现假成功、不误删数据、不承诺未实现能力。
2. **可控**：所有长任务可取消，所有破坏性操作可确认或撤销。
3. **可理解**：主任务、输入成本、当前状态和下一步动作明确。
4. **一致**：导航、卡片、按钮、表单、弹层、反馈和视觉层级全站一致。
5. **可维护**：用共享组件和状态模型收敛重复实现，避免每页各自修补。

### 1.2 修改范围

覆盖正式站：

- 首页与全局导航
- `/gallery`
- `/editor`
- `/ai-generate`
- `/ar-tryon`
- `/nail-analysis`
- `/login`、`/account`、`/privacy`
- 全局设计系统与共享交互组件

不覆盖：

- 独立设计预览 `127.0.0.1:4318`
- 正式识别模型训练与发布门
- 云端同步、商户、订单、支付
- 3D 指甲网格
- 模型 `PRODUCT HOLD` 状态

### 1.3 总原则

1. **先修风险，再做重构，最后统一视觉**。
2. **不因交互优化改变产品能力边界**：
   - 不把辅助识别说成正式识别。
   - 不把本机收录说成云端收藏。
   - 不把待验证 AR 说成已发布质量。
3. **自动化必须给用户控制权**：
   - 可取消。
   - 可复核。
   - 可恢复。
4. **视觉层级必须服务任务**，不为了新拟态效果牺牲可读性和触控目标。

---

## 2. 目标信息架构与共享基础设施

### 2.1 全局导航目标结构

#### 桌面

```text
JiaRu / 甲如
首页    灵感    试戴    创作    我的
[上传照片试色] [灵感图库]
```

#### 移动底部导航

```text
首页    灵感    试戴    创作    我的
```

「分析」不再占据移动底栏常驻位置，改由以下入口承接：

- 首页「找到你的风格」卡片
- AR 或编辑完成后的推荐入口
- 首页 Hero 下的次级入口

> 这是推荐方案。若产品数据显示「分析」是高频主任务，可保留现有五项底栏，但必须给图库另一个稳定入口，不能只靠书签图标。

### 2.2 新增共享组件

#### `AppDialog`

位置：`src/components/ui/AppDialog.tsx`

统一处理：

- `role="dialog"`
- `aria-modal="true"`
- `aria-labelledby`
- 初始焦点
- 焦点圈定
- Escape 关闭
- 焦点恢复
- 背景滚动锁定
- `overscroll-behavior: contain`
- `prefers-reduced-motion` 降级

建议接口：

```tsx
<AppDialog
  open={boolean}
  onClose={() => void}
  title={string}
  description?: string}
  initialFocus?: "first" | "confirm" | "cancel"
  closeOnEsc?: boolean
  closeOnOutside?: boolean
>
  {children}
</AppDialog>
```

适用：

- `NailArtPicker`
- `TextureCropper`
- 清空收录确认
- 更换照片确认
- AR 覆盖确认
- 未来账号敏感操作

#### `ConfirmDialog`

位置：`src/components/ui/ConfirmDialog.tsx`

用于破坏性操作：

```tsx
<ConfirmDialog
  open={boolean}
  title="清空全部收录？"
  description="将永久删除本浏览器中的 N 张收录图片。"
  confirmLabel="清空"
  cancelLabel="取消"
  destructive
  onConfirm={() => void}
  onCancel={() => void}
/>
```

#### `StatusRegion`

位置：`src/components/ui/StatusRegion.tsx`

统一异步反馈：

```tsx
<StatusRegion
  status="idle | loading | success | error"
  message={string}
  severity="info | success | warning | error"
/>
```

要求：

- loading / success 使用 `role="status"` 与 `aria-live="polite"`
- error 使用 `role="alert"`
- loading 文案统一以 `…` 结尾
- 不把计时器放在 live region 内，避免读屏持续播报

#### `UploadTrigger`

位置：`src/components/ui/UploadTrigger.tsx`

替代不可聚焦的 `label + hidden input`。

要求：

- 外层为真实 `<button type="button">`
- 文件输入使用 `sr-only`
- `focus-within` 显示焦点环
- 支持 `accept`、多选、重置文件值
- 上传中可显示 loading

适用：

- AI 参考图
- AR 纹理参考图
- 编辑器照片
- 分析页照片

#### `useAsyncTask`

位置：`src/lib/use-async-task.ts`

目标：

- 统一取消令牌
- 防重复提交
- 区分 `cancelled`、`failed`、`succeeded`
- 组件卸载后不再应用结果

建议状态：

```ts
type AsyncTaskStatus = "idle" | "running" | "cancelled" | "error" | "success";
```

适用：

- AI 生成
- 编辑器识别
- 本机精细抠图
- AR 纹理提取
- 图库收录

---

## 3. Phase 0：发布风险修复

这一阶段必须最先完成，不依赖任何视觉重构。

### 3.1 恢复移动端缩放

#### 问题

当前视口配置禁用了缩放。

#### 修改

删除：

```ts
maximumScale: 1,
userScalable: false,
```

保留：

```ts
width: "device-width",
initialScale: 1,
```

#### 涉及文件

- `src/app/layout.tsx`

#### 验收

- 100%、150%、200% 缩放下：
  - 顶栏不遮挡主内容
  - 底栏不遮挡提交按钮
  - 图库三出口不重叠
  - 编辑器侧栏不溢出
  - AI 生成按钮可达
- 不允许用禁用缩放解决布局问题。

---

### 3.2 图库「清空全部」增加确认

#### 问题

当前一次点击即永久清空。

#### 修改

1. 点击「清空全部」打开 `ConfirmDialog`。
2. 对话框显示当前数量。
3. 确认后执行清空。
4. 清空失败显示 `StatusRegion error`。
5. 清空成功显示成功提示。
6. 单条删除提供 5 秒撤销。

#### 撤销策略

- 删除后暂时保留原记录和 Blob。
- 撤销期限内不释放 object URL。
- 超时后真正删除。
- 刷新页面或组件卸载时立即执行真实删除。

#### 涉及文件

- `src/components/GalleryGrid.tsx`
- `src/lib/gallery-collection.ts`
- `src/components/ui/ConfirmDialog.tsx`
- `src/components/ui/StatusRegion.tsx`

#### 验收

- 一次点击不再直接清空。
- 清空失败不再静默。
- 单条删除可撤销。
- 撤销期间刷新页面不产生“看似还在但实际已删”的假状态。

---

### 3.3 修复 no-op 收录假成功

#### 问题

存储层在无 IndexedDB 时静默 no-op，页面只要 `addCollect` 不抛错就显示成功。

#### 修改

1. 新增 `CollectStorageStatus`：

```ts
export type CollectStorageStatus =
  | "available"
  | "unavailable"
  | "checking"
  | "error";
```

2. 新增 `CollectUnavailableReason`：

```ts
export type CollectUnavailableReason =
  | "indexed_db_missing"
  | "indexed_db_open_failed"
  | "storage_denied"
  | "quota_exceeded"
  | "unknown";
```

3. 新增能力探测：

```ts
export async function probeCollectStorage(): Promise<CollectStorageStatus>;
```

4. 收录必须真实失败：
   - IndexedDB 不可用时，`addCollect` 抛出 `CollectUnavailableError`。
   - UI 不允许显示「已收录到图库」。
   - 收录按钮显示当前浏览器不支持本地收录。

5. 错误分类：

| 错误 | 用户提示 |
|---|---|
| `indexed_db_missing` | 当前浏览器不支持本地收藏 |
| `storage_denied` | 浏览器阻止了本地存储，请检查站点权限 |
| `quota_exceeded` | 本地存储空间不足，请删除部分收录 |
| `fetch_failed` | 图片暂时无法读取，请重试 |
| `not_image` | 返回内容不是图片 |
| `unknown` | 收录失败，请重试 |

6. 写入验证：
   - `addCollect` 写入成功后保存返回 record。
   - 可选执行 `get(record.id)` 回读验证。
   - 回读失败视为收录失败，不显示成功。

#### 涉及文件

- `src/lib/gallery-collection.ts`
- `src/app/ai-generate/page.tsx`
- `src/components/GalleryGrid.tsx`

#### 验收

- 禁用 IndexedDB 后不出现假成功。
- 收录失败有明确原因。
- 成功后可从图库读取。
- SSR 环境不抛错，但 UI 不显示可收录状态。

---

### 3.4 清理超前文案

#### 问题

账号页与登录页承诺了未实现的云端能力；注册流程没有年龄区间选择。

#### 修改

登录页改为：

> 登录后可管理账号资料、登录方式与生图配额。云端作品与跨设备同步正在开发中。

账号页改为：

> 登录后可管理账号资料、登录方式与本地偏好。云端作品同步尚未开放。

年龄区间文案处理：

- 若暂不实现年龄选择，删除该句。
- 若实现，新增注册后年龄选择步骤，并接入「用户改进计划」默认值。

#### 涉及文件

- `src/app/login/page.tsx`
- `src/app/account/page.tsx`
- `src/app/privacy/page.tsx`

#### 验收

- 全站不出现“云端收藏已可用”的暗示。
- 隐私页、登录页、账号页能力表述一致。

---

### 3.5 修正编辑器灵感卡旧文案

#### 问题

灵感卡仍显示旧纯色模型文案，实际行为是预选纹理套装，不自动涂色或贴合。

#### 修改

mini 卡：

> 点击预选「浅粉白星法式」纹理套装

banner 卡：

> 已为你预选相近纹理套装，上传后点击甲面框即可贴合。

失败态：

> 未能提取灵感色，可手动选择纹理套装。

同时删除组件注释里的“涂到手指”表述。

#### 涉及文件

- `src/components/GalleryInspiration.tsx`
- `src/lib/gallery-inspiration.ts`

#### 验收

- 页面文案与白皮书 §4.2 一致。
- `preset === null` 不再永久显示“正在提取”。

---

## 4. Phase 1A：首页与图库重构

### 4.1 首页任务入口重构

#### 当前问题

- Hero 文案偏情绪化，缺少任务说明。
- 「开始试戴」需要摄像头，但首屏未说明。
- 「上传照片试色」是次级按钮，但产品描述中它是核心能力。
- 搜索胶囊实际是图库链接，却使用输入框式凹陷外观。

#### 修改

Hero 结构：

```text
标题：把喜欢的美甲，提前戴在手上
说明：上传一张手部照片试色，或开启摄像头实时试戴。

[上传照片试色]  [开启摄像头实时试戴]

摄像头试戴需要浏览器授权；照片试色默认在本机处理。
```

按钮 priority：

- `上传照片试色`：主按钮。
- `开启摄像头实时试戴`：次级按钮。
- 若产品决定 AR 为主任务，则两者互换，但文案与权限提示不变。

图库入口：

- 将凹陷搜索胶囊改为明确链接：

  > 查看全部灵感款式

- 保留图片图标，但不再使用输入框视觉。

#### 涉及文件

- `src/app/page.tsx`
- `src/app/page.module.css`
- `src/components/Header.tsx`
- `src/components/BottomNav.tsx`

#### 验收

- 首屏 5 秒内可理解两条主路径。
- 摄像头成本在点击前可见。
- 图库入口不再伪装成搜索框。

---

### 4.2 图库卡片动作重构

#### 当前问题

- 三个出口只有图标。
- 图片和标题不可点。
- 与首页整卡可点模型不一致。

#### 修改

1. 卡片默认动作：
   - 图片可点。
   - 标题可点。
   - 默认动作：进入 `/editor?gallery=<id>`。

2. 三出口布局：

桌面：

```text
[试色] [AI 相似款] [AR 试戴]
```

移动：

```text
[试色]
[AI 相似款] [AR 试戴]
```

最窄档：

```text
[试色]
[AI 相似款]
[AR 试戴]
```

3. 语义：
   - 每个按钮保留 `aria-label`。
   - 按钮显示文字，不只显示图标。
   - `AR 试戴` 说明需要摄像头权限。

#### 涉及文件

- `src/components/GalleryGrid.tsx`
- `src/app/gallery/page.tsx`

#### 验收

- 触屏用户不依赖 hover。
- 所有按钮 ≥44×44px。
- 图库与首页卡片交互模型一致。

---

### 4.3 「我的收录」状态模型

#### 目标状态

区块始终存在，不再因空态消失。

#### 状态设计

```ts
type CollectSectionState =
  | "checking"
  | "available"
  | "empty"
  | "load_error"
  | "unavailable";
```

#### UI

| 状态 | 显示 |
|---|---|
| `checking` | 正在读取本机收录… |
| `empty` | 还没有收录。生成结果可一键收录到这里。 |
| `load_error` | 本机收录暂时无法读取。重试 |
| `unavailable` | 当前浏览器不支持本地收录 |
| `available` | 卡片网格 |

#### 删除反馈

- 删除成功显示提示。
- 提供 5 秒撤销。
- 清空成功显示提示。

#### 涉及文件

- `src/components/GalleryGrid.tsx`
- `src/lib/gallery-collection.ts`

#### 验收

- 空态、加载态、失败态可区分。
- 最后一条删除后区块保留。
- 状态更新可被读屏感知。

---

## 5. Phase 1B：编辑器对象模型重构

### 5.1 当前核心矛盾

1. 已有贴合挡住甲面框。
   - 命中顺序为 `placement -> frame`。
   - 用户想换纹理，必须先删除贴合，再点甲面框。
2. 纹理堆叠不适合移动和键盘。
   - 主卡点击直接应用套装。
   - 父容器不可聚焦。
   - 没有 `aria-expanded`。
3. 隐藏框仍可命中。
   - `showFrames` 只隐藏绘制，不关闭 hit-test。
4. 无键盘替代。
   - 画布操作全部依赖 pointer。

### 5.2 目标交互模型

#### 5.2.1 三种对象

```text
甲面框 Frame
贴合实例 Placement
纹理选择 TextureSelection
```

#### 5.2.2 交互优先级

```text
1. 点击已有贴合 -> 选中贴合，打开对象面板
2. 点击空甲面框 -> 使用当前纹理贴合
3. 加框模式点击空白 -> 创建手动框
4. 预览模式点击空白 -> 取消选择
```

关键变化：

- 点击贴合不再吞掉后续操作，而是打开对象面板。
- 对象面板提供 `替换为当前纹理`。
- `showFrames=false` 时进入预览模式，frame hit-test 关闭。

### 5.3 新增对象面板

位置建议：

- 桌面：画布右侧或底部固定面板。
- 移动：底部抽屉。

内容：

```text
当前对象：食指甲面
状态：已贴合「奶茶金饰 / 食指」

[替换为当前纹理]
[微调]
[删除贴合]
```

若选中的是甲面框：

```text
当前对象：食指甲面
状态：未贴合

[用当前纹理贴合]
```

#### 涉及文件

- `src/app/editor/page.tsx`
- `src/components/NailCanvas.tsx`
- `src/components/EditorObjectPanel.tsx` 新增

---

### 5.4 `TextureSetPicker` 重构

#### 5.4.1 状态

```ts
type TexturePickerMode = "collapsed" | "expanded";
```

#### 5.4.2 卡片动作

静止态：

```text
[选择这套] [查看单指]
```

展开态：

```text
拇指 食指 中指 无名指 小指
```

#### 5.4.3 语义

- 主卡容器改为可聚焦。
- 增加 `aria-expanded`。
- `Enter` 展开。
- `Escape` 收起。
- 移动端点击主卡默认展开，不直接应用套装。
- `选择这套` 才设置 `activeSetId`。

#### 5.4.4 「应用全部」独立按钮

```text
[将当前套装应用到全部甲面]
```

点击后：

1. 显示将影响 N 个甲面。
2. 已有贴合将被替换。
3. 用户确认后执行。

#### 涉及文件

- `src/components/TextureSetPicker.tsx`
- `src/app/editor/page.tsx`

---

### 5.5 编辑器键盘替代

#### 对象列表

新增侧栏或抽屉列表：

```text
甲面
- 拇指：已贴合
- 食指：未贴合
- 中指：已贴合
```

键盘操作：

| 键 | 行为 |
|---|---|
| `Tab` | 进入对象列表 |
| `↑ / ↓` | 切换对象 |
| `Enter` | 选中或贴合 |
| `Delete` | 删除贴合或手动框 |
| `← → ↑ ↓` | 微调选中对象 |
| `Ctrl+Z` | 撤销 |

#### 手动框操作

手动框支持：

- 移动
- 缩放
- 旋转
- 删除
- 指位修改

#### 涉及文件

- `src/components/EditorObjectPanel.tsx`
- `src/components/NailCanvas.tsx`
- `src/lib/editor-texture-state.ts`
- `src/lib/canvas/placements.ts`

---

### 5.6 撤销栈升级

#### 当前

只记录 placements。

#### 目标

记录完整编辑快照：

```ts
interface EditorSnapshot {
  frames: NailDetectionRegion[];
  placements: NailPlacement[];
}
```

#### 覆盖操作

- 识别替换 frames
- 手动加框
- 手动框修改
- 贴合
- 替换贴合
- 拖动
- 微调
- 删除
- 重置

#### 涉及文件

- `src/lib/editor-texture-state.ts`
- `src/app/editor/page.tsx`
- `tests/editor-texture-state.test.ts`

---

### 5.7 未保存保护与草稿

#### 5.7.1 更换照片确认

点击「更换照片」时提示将丢弃当前 N 个甲面框和 M 个纹理贴合。

#### 5.7.2 路由离开保护

使用 `beforeunload` 与应用内路由守卫。

#### 5.7.3 本地草稿

阶段一可先做会话内草稿：

- 保存 `frames`
- 保存 `placements`
- 保存纹理选择
- 不保存原图文件

恢复时提示：

> 上次编辑未保存。重新上传原图后可恢复贴合。

阶段二接入 Phase 3 `WorkItem` 后可保存图片 Blob。

#### 涉及文件

- `src/app/editor/page.tsx`
- `src/lib/editor-draft.ts` 新增

---

### 5.8 导出失败治理

#### 当前问题

纹理加载失败会被跳过，仍生成下载。

#### 修改

保存前检查纹理加载状态：

```text
2 个纹理无法加载
[重试加载] [仍要导出] [取消]
```

导出结果：

- 完整成功显示完整保存提示。
- 部分导出显示已导出但跳过 N 个纹理。

#### 涉及文件

- `src/components/NailCanvas.tsx`
- `src/app/editor/page.tsx`

---

## 6. Phase 1C：AI 生图流程重构

### 6.1 请求快照模型

#### 当前问题

生成期间用户可以修改设置，结果与当前 UI 状态脱节；收录元数据读取的是点击收录时的当前值。

#### 新增类型

```ts
interface AiGenerationRequestSnapshot {
  requestId: string;
  engine: Engine;
  prompt: string;
  ratio: AiImageRatio;
  size: string;
  referenceImage: string | null;
  createdAt: number;
}
```

#### 生成流程

1. 点击生成时创建 snapshot。
2. 请求只使用 snapshot。
3. 结果绑定 snapshot。
4. UI 显示当前引擎、尺寸、比例和参考图状态。
5. 收录时保存 snapshot 元数据。

### 6.2 可取消生成

#### 新增状态

```ts
type AiTaskStatus =
  | "idle"
  | "running"
  | "cancelled"
  | "error"
  | "success";
```

#### UI

生成中显示运行中提示、已等待秒数和取消按钮。

取消后显示：

> 已取消本次生成。当前设置已保留。

#### 请求规则

- 使用 `AbortController`。
- 请求完成后检查是否已取消。
- 取消不算失败。
- 不自动重试。
- 不清空上一版结果。

### 6.3 保留上一版结果

#### 当前问题

重新生成会先清空旧图。

#### 修改

- 生成期间保留上一版结果。
- 新图成功后替换主结果。
- 上一版折叠显示。
- 支持一键切回上一版。

### 6.4 引擎状态独立

#### 问题

切换引擎会强制重置尺寸，且长提示词进入非法状态。

#### 修改

```ts
interface EngineSettings {
  size: string;
  lastPromptDraft: string;
}
```

规则：

- 每个引擎保存自己的尺寸。
- 切回引擎时恢复上次尺寸。
- 提示词超过当前引擎上限时：
  - 显示错误
  - 禁用生成
  - 提供返回原引擎或手动缩短

### 6.5 表单可访问性

| 控件 | 修改 |
|---|---|
| 主提示词 | 增加可见 label「设计描述」 |
| 引擎 | radiogroup / `aria-pressed` |
| 画面比例 | radiogroup / `aria-pressed` |
| 输出尺寸 | radiogroup / `aria-pressed` |
| 参考图上传 | `UploadTrigger` |
| 生成结果 | `StatusRegion` |
| 收录结果 | `StatusRegion` |

### 6.6 错误分类

| 错误 | 用户提示 |
|---|---|
| 空提示词 | 请先描述想要的美甲 |
| 提示词超限 | 当前引擎最多支持 300 字 |
| 未配置密钥 | AI 服务暂未配置，请联系管理员 |
| 配额超限 | 今日生成次数已用完，明天再试 |
| 网络失败 | 生成请求失败，请重试 |
| 上游超时 | 生成超时，请重试或更换引擎 |
| 结果无效 | AI 服务返回异常，请重试 |

---

## 7. Phase 1D：AR 三步流程重构

### 7.1 目标流程

```text
Step 1 选择来源
  - 上传参考图
  - 上传单纹理
  - 开启实时摄像头

Step 2 提取与复核
  - 自动识别
  - 精细抠图
  - 指位修正
  - 低置信复核
  - 应用预览

Step 3 试戴与校准
  - 开启摄像头
  - 当前指高亮
  - 五指校准
  - 关闭摄像头
```

顶部显示步骤状态。

---

### 7.2 低置信覆盖前复核

#### 当前问题

低置信候选会自动提取并直接覆盖旧配置。

#### 新规则

1. 当前没有旧纹理：
   - 高置信：自动应用。
   - 中置信：自动应用，显示可复核提示。
   - 低置信：进入复核态。

2. 已有旧纹理：
   - 高置信：显示替换预览。
   - 中低置信：必须确认。

复核界面显示：

```text
已识别 5 个甲面
其中 2 个建议复核

[应用到试戴] [继续调整] [取消]
```

应用后提供撤销提示。

---

### 7.3 摄像头会话控制

#### 当前问题

就绪后没有主动关闭按钮。

#### 修改

新增：

```text
[关闭摄像头]
```

点击后：

- 停止全部 track
- 关闭 Hands 实例
- 解绑 `video.srcObject`
- 回到初始态
- 焦点返回开启按钮

#### 连续失败状态

增加失败计数：

- 连续 30 帧推理失败。
- 或 3 秒无有效关键点且持续异常。

显示：

```text
手部识别暂时失败
[重试] [改用上传照片试色]
```

---

### 7.4 当前指校准高亮

#### 修改

`ArView` 新增 prop：

```ts
activeFinger?: number;
```

效果：

- 当前校准指甲使用珊瑚描边。
- 校准面板显示当前手指。
- 显示已调整数量。

#### 校准引导

```text
请展示手背，张开五指。
选择一个手指后，拖动滑杆调整长度和宽度。
```

---

### 7.5 弹层统一

`NailArtPicker` 与 `TextureCropper` 改用 `AppDialog`。

要求：

- Escape 可关闭。
- 提取中关闭视为取消。
- 取消后不再应用结果。
- 焦点恢复到打开按钮。
- `TextureCropper` 提供键盘选区。

---

### 7.6 诊断信息降级

将以下内容放入「技术详情」折叠区：

- Worker 耗时
- 模型版本
- 诊断 JSON
- 逐步摄像头日志

主界面只保留：

- 当前状态
- 用户可执行操作
- 关键警告

---

## 8. Phase 2：视觉系统收敛

### 8.1 视觉目标

保留品牌基底：

- 暖纸底色
- 珊瑚强调
- 中文衬线标题
- 真实美甲近景
- 五指与甲片色票母题

减少：

- 所有卡片同等外阴影
- 重复英文眉题
- 输入式链接
- 9–10px 主流程文字
- 无意义动效

### 8.2 三级层级

#### Level 1：静态内容

- 细边框
- 极浅阴影或无阴影
- 不浮起

适用：

- 隐私说明
- 能力边界说明
- 纯文本信息

#### Level 2：可交互

- 外凸阴影
- hover 阴影增强
- active 转内凹
- 明确光标与焦点

适用：

- 卡片
- 按钮
- 上传区

#### Level 3：输入 / 选中 / 按下

- 内凹
- 珊瑚描边
- 焦点环

适用：

- 输入框
- 选中 chip
- 当前导航项

### 8.3 字号系统

| 用途 | 最小值 |
|---|---|
| 主操作按钮 | 14px |
| 正文 | 14px |
| 表单标签 | 12px |
| 辅助说明 | 12px |
| 高对比小标签 | 12px |
| 状态提示 | 13px |

禁止：

- 主流程使用 9px、9.5px、10px 文字。
- 触控按钮文字低于 11px。

### 8.4 对比度

| 元素 | 标准 |
|---|---|
| 正文与小文字 | ≥4.5:1 |
| 有效图标 | ≥3:1 |
| 焦点环 | 明显高于背景 |
| Hero 覆盖文字 | 使用实底或强阴影，不依赖照片局部亮度 |

### 8.5 动效统一

所有交互动效：

- 只动画 `transform` 与 `opacity`
- 不使用 `transition: all`
- 支持 `prefers-reduced-motion`
- 按压反馈无布局位移
- 页面装饰动效不超过一次

优先保留：

- NeuToggle 磁吸回弹
- 弹层显隐
- 卡片选中脉冲

降级：

- GalleryGrid hover 缩放
- AR spin / pulse
- TextureCropper spinner

---

## 9. Phase 3：本地 WorkItem 作品模型

### 9.1 目标

把分散的 `gallery`、`collect`、`preset` 参数升级为统一的本地作品对象。

### 9.2 数据模型

```ts
type WorkItemType =
  | "ai-result"
  | "editor-result"
  | "ar-config";

interface WorkItem {
  id: string;
  type: WorkItemType;
  title: string;
  previewBlob: Blob;
  createdAt: number;
  updatedAt: number;
  storageStatus: "local-only";
  source: {
    engine?: string;
    prompt?: string;
    textureSetId?: string;
    galleryId?: string;
    collectId?: string;
  };
  metadata: Record<string, unknown>;
}
```

### 9.3 存储设计

- IndexedDB 库：`jiaru-works`
- Store：`works`
- 与现有 `jiaru-gallery` 并存
- 提供迁移工具：
  - 将旧 `collects` 迁移为 `ai-result`
  - 不删除旧库，直到验证完成

### 9.4 跨页参数

推荐统一为：

```text
?work=<workId>
```

兼容旧参数：

```text
?gallery=
?collect=
?preset=
```

### 9.5 页面行为

| 来源 | 目标 | 参数 |
|---|---|---|
| AI 结果 | AR | `?work=<id>` |
| AI 结果 | 编辑器 | `?work=<id>` |
| 图库款式 | 编辑器 | `?work=<id>` |
| 图库款式 | AI | `?work=<id>` |
| 分析推荐 | 编辑器 | `?work=<id>` |

### 9.6 明确边界

WorkItem 仍是本机存储：

> 仅保存在此浏览器

不得显示：

- 云端已保存
- 已跨设备同步
- 已发布

---

## 10. 测试与验收计划

### 10.1 单元测试

新增或扩展：

| 测试文件 | 覆盖 |
|---|---|
| `tests/gallery-collection-status.test.ts` | 存储不可用、写入失败、错误分类 |
| `tests/editor-object-state.test.ts` | 对象选择、替换、撤销、预览模式 |
| `tests/editor-draft.test.ts` | 草稿保存、恢复、失效 |
| `tests/ai-generation-task.test.ts` | 快照、取消、防重复、结果绑定 |
| `tests/ar-review-flow.test.ts` | 低置信确认、取消竞态、覆盖撤销 |
| `tests/work-item-store.test.ts` | WorkItem 增删改查、迁移 |

### 10.2 组件测试

覆盖：

- `AppDialog` 焦点圈定与恢复
- `ConfirmDialog` 破坏性确认
- `StatusRegion` live region
- `UploadTrigger` 键盘可达
- `TextureSetPicker` 移动端与键盘展开
- `GalleryGrid` 状态模型

### 10.3 浏览器 E2E

必须串行执行：

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd run start
```

浏览器场景：

1. 首页 → 上传试色
2. 首页 → AR 试戴
3. 图库 → 编辑器
4. 图库 → AI
5. AI 生成 → 收录 → 图库 → AR
6. 编辑器上传 → 识别 → 贴合 → 导出
7. AR 上传参考图 → 复核 → 校准 → 关闭摄像头
8. 登录 → 账号 → 编辑资料

### 10.4 可访问性验收

- 键盘完成编辑器主流程
- 键盘完成 AI 生成主流程
- 键盘完成 AR 提取复核
- 所有 icon-only 控件有 `aria-label`
- 所有表单有可见或可编程标签
- 200% 缩放无功能丢失
- 焦点不被 sticky header / footer 遮挡

### 10.5 响应式验收

视口：

- 320px
- 375px
- 390px
- 640px
- 768px
- 1024px
- 1280px
- 1440px

重点：

- 图库三出口
- 编辑器侧栏
- AI 结果按钮
- AR 控制面板
- 移动底栏
- 软键盘
- 安全区

---

## 11. 实施顺序与交付批次

### Batch 1：P0 修复

范围：

1. 恢复缩放
2. 清空确认
3. no-op 收录治理
4. 超前文案清理
5. 灵感卡旧文案

预计改动文件：

- `src/app/layout.tsx`
- `src/components/GalleryGrid.tsx`
- `src/lib/gallery-collection.ts`
- `src/app/ai-generate/page.tsx`
- `src/app/login/page.tsx`
- `src/app/account/page.tsx`
- `src/components/GalleryInspiration.tsx`

交付要求：

- lint 0
- typecheck 0
- 相关测试通过
- 全量测试通过
- 生产构建通过

### Batch 2：共享基础设施

范围：

1. `AppDialog`
2. `ConfirmDialog`
3. `StatusRegion`
4. `UploadTrigger`
5. `useAsyncTask`

不直接替换全部页面，只先接入：

- 图库清空确认
- AI 参考图上传
- AI 状态反馈

### Batch 3：首页与图库

范围：

1. Hero 任务说明
2. 图库导航位置
3. 图库三出口
4. 收录状态模型
5. 触控目标修复

### Batch 4：编辑器

范围：

1. 对象面板
2. 纹理选择器
3. 键盘对象列表
4. 撤销栈
5. 草稿保护
6. 导出失败提示

### Batch 5：AI

范围：

1. 请求快照
2. 取消生成
3. 上一版结果
4. 引擎状态
5. 表单可访问性
6. 收录元数据绑定

### Batch 6：AR

范围：

1. 三步流程
2. 低置信复核
3. 摄像头关闭
4. 当前指高亮
5. Dialog 统一
6. 诊断折叠

### Batch 7：视觉收敛

范围：

1. 三级层级
2. 字号令牌
3. 对比度修复
4. reduced-motion 覆盖
5. 首页与图库视觉重评

### Batch 8：WorkItem

范围：

1. 本地作品 store
2. 旧收录迁移
3. 跨页参数统一
4. AI / AR / 编辑器接入

---

## 12. 风险与对策

| 风险 | 对策 |
|---|---|
| 恢复缩放后布局溢出 | 200% 缩放专项回归；优先修布局，不回退禁缩放 |
| 移动底栏移除「分析」降低曝光 | 首页保留分析卡；AR / 编辑完成页增加分析入口 |
| 图库按钮加文字后密度过高 | 窄屏改两行或单列，不缩小字号 |
| 编辑器对象面板挤压画布 | 移动端使用底部抽屉；默认收起 |
| 撤销栈扩展引入状态错乱 | EditorSnapshot 单元测试覆盖全部操作 |
| AI 取消与服务端超时竞争 | 前端取消只影响 UI，不宣称服务端任务终止 |
| AR 复核增加步骤 | 高置信路径保留一键应用 |
| Dialog 重构影响现有弹层 | 先新增共享组件，再逐个迁移，不一次性替换 |
| WorkItem 迁移造成旧收录丢失 | 旧库只读迁移，验证后保留一个版本周期 |
| 视觉收敛削弱品牌 | 保留暖纸、珊瑚、衬线和甲片母题，只减少无效阴影 |

---

## 13. Definition of Done

每个 Batch 完成时必须同时满足：

1. 相关源码修改完成。
2. 相关单元与组件测试通过。
3. 浏览器关键路径手动验收通过。
4. `lint`、`typecheck`、全量测试、生产构建串行通过。
5. 无假成功、无不可逆误删、无未承诺能力文案。
6. 白皮书对应章节更新，版本顺延。
7. 当日 `dev-log/YYYY-MM-DD.md` 记录变更。
8. 若涉及 Goal 或模型质量边界，不改写 `PRODUCT HOLD`。

---

## 14. 文档维护说明

- 本文档是前端交互改造的成套方案，不替代白皮书接口合同。
- 实施任意 Batch 时，必须同步更新：
  - `docs/technical-whitepaper.md` 对应章节
  - 当日 `dev-log/YYYY-MM-DD.md`
- 本文档仅记录方案目标、范围、步骤与验收门，不登记实验过程细节。
