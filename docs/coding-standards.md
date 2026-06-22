# 开发规范 — 甲如

## 1. 代码风格

### 命名规范
```
文件名:        kebab-case (如 nail-canvas.tsx)
组件名:        PascalCase (如 NailCanvas)
函数名:        camelCase (如 handleSave)
变量名:        camelCase (如 selectedColor)
常量名:        UPPER_SNAKE (如 PRESET_COLORS)
类型/接口:     PascalCase 前缀 I (如 INailArt)
```

### 文件组织
```
每个组件一个文件
页面组件放在 app/ 目录
可复用组件放在 components/ 目录
工具函数放在 lib/ 目录
```

## 2. 组件规范

### React 组件结构
```tsx
// 1. 导入
'use client'
import { useState } from 'react'

// 2. 类型定义
interface NailCanvasProps {
  imageUrl: string
  selectedColor: string
}

// 3. 组件函数
export function NailCanvas({ imageUrl, selectedColor }: NailCanvasProps) {
  // 3a. 状态
  const [isDrawing, setIsDrawing] = useState(false)
  
  // 3b. 事件处理
  const handleMouseDown = () => { ... }
  
  // 3c. 渲染
  return ( ... )
}
```

## 3. 工作流程

### 开发步骤
1. 查看 dev-log/ 了解进度
2. 检查 docs/ 确认需求/设计
3. 实现功能（小步提交）
4. 更新 dev-log/ 记录完成事项
5. 如有技术决策更新对应 docs/

### 提交规范
```
每次完成一个独立功能点
不可逆操作前先确认
每天结束前更新开发日志
```

## 4. 隐私保护规范（强制执行）

```
1. 用户照片处理必须在前端完成
2. 不得将用户原图发送到任何外部服务
3. AI生成只发送文本描述
4. AR摄像头数据只在内存中处理
5. 所有隐私相关的代码要有注释说明
```

## 5. 浏览器兼容性

```
支持: Chrome 90+, Safari 15+, Edge 90+
移动端: iOS Safari 15+, Android Chrome 90+
Canvas API: 全支持
Camera API: 需 HTTPS 环境
```
