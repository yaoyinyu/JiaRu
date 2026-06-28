# Phase 2 AI 生成模块 — 技术方案与任务分解

## 1. 目标

实现用户输入文字描述 → AI 生成美甲效果图的完整链路。

## 2. 架构设计

```
[用户输入 prompt] 
    ↓
[POST /api/generate-ai]  ← 服务端，持有 API Key
    ↓
[OpenAI DALL-E 3 API]    ← 图像生成
    ↓
[返回 image URL]
    ↓
[前端显示 + 保存]
```

### 关键设计决策

1. **服务端 API 路由**：API Key 只存在服务端 `.env.local`，前端永远拿不到
2. **Prompt 工程**：用户输入 + 美甲场景词后缀，确保生成结果与美甲相关
3. **图片返回方式**：DALL-E 3 返回 URL，前端直接显示；保存时通过 canvas 转 blob 下载

## 3. 任务分解（含验收标准）

### Task 1: API 路由实现

**文件**: `src/app/api/generate-ai/route.ts`

**实现要点**:
- POST 请求，body: `{ prompt: string }`
- 校验 prompt 非空，长度 1-500
- 调用 OpenAI Images API（DALL-E 3, 1024x1024, standard quality）
- prompt 加后缀：`", nail art design on fingernails, manicure, close-up, beautiful"`
- 返回 `{ imageUrl: string }`
- 错误处理：
  - 400: prompt 为空或过长
  - 401: API Key 无效
  - 429: 速率限制
  - 500: 其他服务端错误

**验收标准**:
- [ ] POST 请求返回 200 + `{ imageUrl: string }`
- [ ] 空 prompt 返回 400
- [ ] prompt > 500 字符返回 400
- [ ] API Key 无效时返回 401 + 友好错误
- [ ] 代码无 `any` 类型

### Task 2: 前端页面改造

**文件**: `src/app/ai-generate/page.tsx`

**实现要点**:
- handleGenerate() 调用 `/api/generate-ai`
- loading 状态显示 spinner
- 生成成功显示图片
- 保存按钮：fetch image URL → canvas → toBlob → 下载
- 错误显示在图片区域，红色边框
- 保留现有 10 个 AI_STYLES 预设按钮

**验收标准**:
- [ ] 输入文本 → 点击生成 → 显示 loading → 显示图片
- [ ] 10 个预设风格按钮可用
- [ ] 保存按钮可下载图片到本地
- [ ] 网络错误显示友好提示
- [ ] 隐私文案「只发送文字描述，不发送照片」始终可见
- [ ] 生成中按钮禁用
- [ ] ESLint 0 errors

### Task 3: 环境变量配置

**文件**: `.env.local.example`

**实现要点**:
- 示例文件提交到 git
- 真实 `.env.local` 不提交（已在 .gitignore 中）

**验收标准**:
- [ ] `.env.local.example` 含 `OPENAI_API_KEY=your-key-here`
- [ ] README 或文档说明如何配置

## 4. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 用户无 OpenAI API Key | 代码写好但运行时检测无 Key 返回友好错误 |
| 生成结果与美甲无关 | Prompt 后缀强制关联 |
| API 超时 | 30s 超时，前端显示重试按钮 |
| 成本控制 | 每次生成都消耗 API 额度，未来可加限流 |

## 5. 未来扩展

- 多模型支持（Stable Diffusion 本地部署）
- 历史记录（localStorage）
- 生成参数调整（尺寸、质量、风格强度）
