# Phase 2 AI 生成模块 — 任务卡

## 目标
实现 AI 美甲生成完整功能，用户输入文字描述，AI 生成美甲效果图。

## 验收标准

- [ ] 输入描述文本 → 调用 OpenAI DALL-E 3 生成图片
- [ ] 10 个预设风格按钮可用，点击后填入对应描述
- [ ] 生成中显示 loading 动画（不能阻塞 UI）
- [ ] 生成成功后显示图片 + 保存按钮
- [ ] 保存按钮可下载图片到本地
- [ ] 隐私文案「只发送文字描述，不发送照片」始终可见
- [ ] API 错误时显示友好错误提示（不崩溃）
- [ ] ESLint 0 errors

## 技术方案

### API 路由
`src/app/api/generate-ai/route.ts`
- POST 请求，body: `{ prompt: string }`
- 调用 OpenAI Images API (DALL-E 3)
- prompt 加「美甲、指甲 art」后缀以确保相关性
- 返回 `{ imageUrl: string }`
- 错误码 400/500 有明确提示

### prompt 工程
```
用户输入 + ", nail art design, manicure, beautiful"
```

### 前端页面
扩展现有 `src/app/ai-generate/page.tsx`：
- handleGenerate() → 调用 `/api/generate-ai`
- 保存按钮 → 下载图片

### 安全
- API Key 只存在服务端 `.env.local`
- 不接受用户传图片，只接受纯文本

## 文件清单

| 文件 | 操作 |
|------|------|
| `src/app/api/generate-ai/route.ts` | 新建 |
| `src/app/api/generate-ai/.env.local.example` | 新建（示例） |
| `src/app/ai-generate/page.tsx` | 修改 |
| `.env.local` | 姚哥手动创建（不放 git） |

## 风险
- 姚哥需提供 OpenAI API Key
- 方案：先写好代码，等姚哥提供 Key 后填入即可运行
