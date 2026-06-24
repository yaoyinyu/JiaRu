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

## 6. AR 模块开发经验教训

### 6.1 阈值设计必须避免覆盖关系

**问题**: 两个阈值 `NAIL_VISIBLE=0.002` < `NAIL_AMBIGUOUS=0.004` 产生了包含关系，导致第一个分支几乎覆盖所有情况，逻辑恒为 true。

**规则**: 设计多阈值时画数轴覆盖范围，确保每个分支有独立作用域。两个阈值的分支不应有包含关系。

### 6.2 先实测物理方向，再写代码逻辑

**问题**: MediaPipe z 轴朝向镜头为负值（定义，非直觉）。手心朝镜头时 TIP.z > DIP.z（指尖比关节更远离镜头），手背朝镜头时 TIP.z < DIP.z。

**规则**: 方向类判断先 `console.log` 打印关键值确认方向，再写代码。不要凭直觉写 z 方向判断。

### 6.3 useEffect 依赖数组陷阱

**问题**: `userStarted` 加到 useEffect 依赖数组导致 HMR 报错。

**规则**: 动态状态变量不要直接进 useEffect 依赖数组，用 `useRef` + `requestAnimationFrame` 循环替代。

### 6.4 手机端 getUserMedia 交互限制

**问题**: 自动调用 `getUserMedia` 被移动端浏览器隐私策略拦截。

**规则**: 移动端所有需要权限的 API（摄像头/麦克风/位置等）都必须绑定用户手势事件触发。

### 6.5 移除 camera_utils 依赖

**问题**: `@mediapipe/camera_utils` 在移动端不兼容。

**规则**: 使用原生 `getUserMedia` + `requestAnimationFrame` 循环替代第三方摄像头工具库。

### 6.6 CSS object-cover 坐标系问题

**问题**: CSS `object-cover` 裁剪视频导致 canvas 坐标系与 video 显示尺寸不匹配，纹理错位。

**规则**: canvas 使用 CSS 显示尺寸，landmarks 坐标需要根据裁剪偏移进行变换。
