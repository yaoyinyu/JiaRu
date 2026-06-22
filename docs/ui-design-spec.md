# UI设计规范 — 甲如

## 1. 品牌色

```
主色调（品牌色）：
  - 玫瑰粉（主色）:    #E8A0BF
  - 深玫瑰（强调色）:  #D4749D
  - 极浅粉（背景色）:  #FFF5F7
  - 纯白（背景色）:    #FFFFFF
  - 深灰（文字色）:    #4A4A4A

辅助色：
  - 浅灰（次要文字）:  #9CA3AF
  - 粉色渐变:          from #FFF5F7 to #FFE4EC
```

## 2. 字体

```
中文字体: PingFang SC, Microsoft YaHei, Noto Sans SC, sans-serif
英文字体: Inter, system-ui, sans-serif
字号系统: text-xs(12) / sm(14) / base(16) / lg(18) / xl(20) / 2xl(24) / 3xl(30)
```

## 3. 组件规范

### 按钮
```
圆角: rounded-2xl (16px) 或 rounded-full
最小高度: 48px（触屏友好）
内边距: px-6 py-3
阴影: shadow-sm, hover:shadow-md
动效: transition-all duration-200, active:scale-95
```

### 卡片
```
圆角: rounded-2xl
内边距: p-4 或 p-6
阴影: shadow-sm
背景: bg-white
边框: border border-pink-100
```

### 颜色选择按钮
```
圆形: rounded-full
尺寸: w-10 h-10 (40px, 触屏友好)
选中态: ring-2 ring-offset-2 ring-pink-400
```

### 导航栏
```
高度: h-16 (64px)
背景: bg-white/80 backdrop-blur-md
固定: fixed top-0
```

## 4. 页面布局

### 首页
```
Logo + 品牌名称（顶部居中）
四个功能入口（网格2×2或垂直排列）
底部标语
```

### 编辑器
```
顶部: 返回按钮 + 标题
中间: 照片画布（全宽自适应）
底部: 颜色选择面板 + 操作按钮（撤销/重置/保存）
```

### 移动端适配
```
断点: sm(640px) / md(768px) / lg(1024px)
优先移动端设计，按钮最小48px
触摸目标间距 ≥ 8px
```

## 5. 交互动效

```
按钮点击: scale 0.97 → 1.0
页面切换: fade in (opacity 0→1, 300ms)
颜色选中: ring 缩放动画
保存成功: 短暂显示 ✓ 提示
```
