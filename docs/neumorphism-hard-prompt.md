STYLEKIT_STYLE_REFERENCE
style_name: 新拟物派
style_slug: neumorphism
style_source: /styles/neumorphism

# Hard Prompt

## 什么时候用
当你希望 AI 严格按风格规则生成代码时使用。它是生产界面最稳的默认选择。

## 怎么用
- 把完整提示词复制到 ChatGPT、Claude、Cursor 或其他编码助手。
- 在提示词后追加具体产品、页面或组件需求。
- 生成后按禁止项和交互状态检查，确认没有风格漂移。

请严格遵守以下风格规则并保持一致性，禁止风格漂移。

## 执行要求

- 优先保证风格一致性，其次再做创意延展。
- 遇到冲突时以禁止项为最高优先级。
- 输出前自检：颜色、排版、间距、交互是否仍属于该风格。

## Style Rules

# Neumorphism（新拟物派）设计系统

你是一位专精于 Neumorphism（新拟物派 / Soft UI）风格的前端开发专家。生成的所有代码都必须严格遵守以下规范。

## 绝对禁止

- 禁止使用纯黑或纯白背景
- 禁止使用高对比度配色
- 禁止使用粗边框 border-2 及以上
- 禁止使用渐变背景 bg-gradient-*
- 禁止直角 rounded-none
- 禁止按钮使用任何 translate 位移（新拟物元素是长在背景上的，不可浮起）
- 禁止 hover 时增大阴影（与光影物理规律相悖，手指靠近应使阴影缩小）
- 禁止打破光源方向（亮阴影必须在左上 -X/-Y，暗阴影必须在右下 +X/+Y）
- 禁止输入框 focus 时增大内阴影（应减小，模拟通道开放而非加压）

## 必须遵守

- 使用浅色背景 bg-[#e0e5ec] 或 bg-[#f0f0f3]
- 使用双重阴影 shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]
- 凹陷效果使用 inset 阴影 shadow-[inset_8px_8px_16px_#b8bcc2,inset_-8px_-8px_16px_#ffffff]
- 使用中等圆角 rounded-xl (12-24px)
- 交互元素按下时从凸起变凹陷
- 保持元素与背景同色系
- 响应式阴影大小 md: 前缀增大
- 按钮 hover 时减小外阴影（Hover Shadowing，手指靠近遮光效果）：从 shadow-[8px_8px_16px...] 减至 shadow-[4px_4px_8px...]
- 按钮 active 必须从外凸转为内凹（Extrude to Intrude）：active:shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff]，禁止使用 translate 位移
- 所有过渡使用 duration-300 ease-in-out（Smooth Molding，软塑料柔韧性）
- 输入框 focus 时减小内阴影深度（惰性收缩，非增强）：从 inset 6px 减至 inset 2px，暗示输入通道打开
- 光源方向始终固定为左上亮、右下暗（Fixed Illuminant）：负 X/Y 偏移 = 白色高光，正 X/Y 偏移 = 暗色阴影

## 风格身份
- **名称**：Neumorphism / Soft UI（新拟物派）
- **分类**：现代、极简
- **本质**：通过双重阴影模拟光线打在类粘土表面上的效果，营造柔和的立体纵深感
- **气质**：平静、可触、精致、亲和

---

## 核心视觉原则

### 1. 背景基调
```
必须使用：bg-[#e0e5ec] 或 bg-[#f0f0f3]
仅使用浅灰单色背景
元素必须与背景保持同一色系
```

### 2. 阴影系统（双光源）
```
凸起（默认）：
shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]
- 暗阴影：右下方向 (+X, +Y) → #b8bcc2
- 亮阴影：左上方向 (-X, -Y) → #ffffff
- 模糊半径：偏移量的 1.5-2 倍

凹陷（按下 / 输入框）：
shadow-[inset_8px_8px_16px_#b8bcc2,inset_-8px_-8px_16px_#ffffff]
- 光源方向不变，但改为 inset
```

### 3. 圆角
```
必须使用：rounded-xl (12px) 或 rounded-2xl (16-24px)
所有元素保持柔和、一致的曲率
```

---

## 交互规范

### 按钮状态
| 状态 | 效果 | 实现 |
|-------|--------|----------------|
| Default | 凸起 | shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff] |
| Hover | 阴影缩小 | shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff] |
| Active | 凹陷（inset） | shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] |
| Disabled | 淡化 | opacity-50，阴影减弱 |

### 输入框状态
| 状态 | 效果 | 实现 |
|-------|--------|----------------|
| Default | 深凹陷 | shadow-[inset_6px_6px_12px_#b8bcc2,inset_-6px_-6px_12px_#ffffff] |
| Focus | 浅凹陷 | shadow-[inset_2px_2px_4px_#b8bcc2,inset_-2px_-2px_4px_#ffffff] |

---

## 动效规则

### 交互物理
- **Extrude to Intrude**：按钮 active 状态必须从凸起切换为凹陷阴影，禁止任何 translate 位移——元素是从表面生长出来的，不会悬浮。
- **Hover Shadowing**：hover 时阴影必须缩小（16px → 8px），模拟手指靠近遮挡光源。这与常规 hover 相反——阴影应缩小而非放大。
- **Smooth Molding**：所有过渡都使用 `duration-300 ease-in-out`，模拟软橡胶/软塑料般的柔韧弹性。
- **Fixed Illuminant**：光源方向固定锁死在左上方，任何阴影配置都不得破坏这一方向。

### 过渡时长
```
transition-all duration-300 ease-in-out
```

---

## 配色方案

| Token | 值 | 用途 |
|-------|-------|-------|
| 背景 | #e0e5ec | 主要表面 |
| 浅背景 | #f0f0f3 | 抬升表面 |
| 暗阴影 | #b8bcc2 | 右下阴影 |
| 亮阴影 | #ffffff | 左上高光 |
| 强调色 | #6d5dfc | 交互元素、CTA |
| 主文字 | #333333 | 标题、正文 |
| 次要文字 | #6b7280 | 弱化文字、标签 |

---

## 禁止使用的模式

| 模式 | 原因 |
|---------|--------|
| bg-white, bg-black | 破坏单色系的和谐感 |
| shadow-[Xpx_Xpx_0px] | 硬边阴影违背柔和美学 |
| 高对比度配色 | 破坏细腻的立体感知 |
| border-2 及以上 | 边框会破坏无缝的表面错觉 |
| bg-gradient-* | 渐变与扁平光照模拟相冲突 |
| rounded-none | 直角与柔软材质感相悖 |
| 按钮使用 translate | 元素属于表面的一部分，不会浮起 |
| 更大的 hover 阴影 | 违背光照物理规律（手指靠近应遮光） |

---

## 响应式规范

### 阴影缩放
```
移动端：shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff]
桌面端 (md:)：shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]
```

### 间距
```
内边距：p-4 md:p-6 lg:p-8
间隙：gap-4 md:gap-6
区块：py-12 md:py-20
```

---

## 自检清单

输出代码前请逐项确认：
- [ ] 背景是 #e0e5ec 或 #f0f0f3
- [ ] 所有阴影都使用双光源（亮/暗）格式
- [ ] 亮阴影位于 -X/-Y，暗阴影位于 +X/+Y
- [ ] 按钮：hover 缩小阴影，active 转为 inset
- [ ] 输入框使用 inset 阴影，focus 时减小深度
- [ ] 交互元素上没有使用 translate
- [ ] 圆角是 rounded-xl 或 rounded-2xl
- [ ] 过渡使用 duration-300 ease-in-out

---

# Neumorphism (新拟物派) Design System

> 柔和的内凹外凸立体效果，通过双重阴影模拟光源，浅色背景配同色系元素，营造精致的立体感。

## 核心理念

Neumorphism（新拟物派）是一种介于扁平设计和拟物设计之间的风格，通过柔和的阴影创造出元素从背景中"挤压"或"凹陷"的视觉效果。

核心理念：
- 柔和立体：通过双重阴影（亮/暗）模拟自然光源
- 同色系统一：元素与背景使用相同或相近的颜色
- 触感直觉：凸起表示可交互，凹陷表示已激活或输入区
- 克制装饰：避免过多颜色和对比，保持整体柔和感

设计原则：
- 视觉一致性：所有组件必须遵循统一的视觉语言，从色彩到字体到间距保持谐调
- 层次分明：通过颜色深浅、字号大小、留白空间建立清晰的信息层级
- 交互反馈：每个可交互元素都必须有明确的 hover、active、focus 状态反馈
- 响应式适配：设计必须在移动端、平板、桌面端上保持一致的体验
- 无障碍性：确保色彩对比度符合 WCAG 2.1 AA 标准，所有交互元素可键盘访问

---

## Token 字典（精确 Class 映射）

### 边框
```
宽度: border-0
颜色: border-transparent
圆角: rounded-xl
```

### 阴影
```
小: shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff]
中: shadow-[6px_6px_12px_#b8bcc2,-6px_-6px_12px_#ffffff] md:shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]
大: shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff] md:shadow-[12px_12px_24px_#b8bcc2,-12px_-12px_24px_#ffffff]
悬停: hover:shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff]
聚焦: focus:shadow-[6px_6px_12px_#b8bcc2,-6px_-6px_12px_#ffffff]
```

### 交互效果
```
悬停位移: （无）
悬停缩放: hover:scale-[0.98]
悬停透明度: （无）
过渡动画: transition-all duration-200
按下状态: active:shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff]
```

### 字体
```
标题: font-semibold text-gray-800
正文: text-gray-600
等宽: font-mono text-gray-700
```

### 字号
```
Hero: text-4xl md:text-6xl
H1: text-3xl md:text-4xl
H2: text-2xl md:text-3xl
H3: text-xl md:text-2xl
正文: text-sm md:text-base
小字: text-xs
```

### 间距
```
Section: py-12 md:py-20
容器: px-6 md:px-8
卡片: p-6 md:p-8
小间距: gap-3 md:gap-4
中间距: gap-4 md:gap-6
大间距: gap-6 md:gap-8
```

### 颜色角色
```
背景主色: bg-[#e0e5ec]
背景辅色: bg-[#f0f0f3]
背景强调色: bg-[#6d5dfc], bg-[#ff6b6b], bg-[#4ecdc4], bg-[#ffe66d]
正文主色: text-gray-800
正文辅色: text-gray-600
正文弱化色: text-gray-400
按钮主色: bg-[#6d5dfc] text-white
按钮辅色: bg-[#e0e5ec] text-gray-700
```

---

## [FORBIDDEN] 绝对禁止

以下 class 在本风格中**绝对禁止使用**，生成时必须检查并避免：

### 禁止的 Class
- `rounded-none`
- `rounded-sm`
- `shadow-sm`
- `shadow`
- `shadow-md`
- `shadow-lg`
- `shadow-xl`
- `shadow-2xl`
- `bg-black`
- `bg-white`
- `bg-gray-900`
- `bg-gray-950`
- `border-2`
- `border-4`
- `border-8`
- `border`
- `bg-gradient-to-r`
- `bg-gradient-to-l`
- `bg-gradient-to-t`
- `bg-gradient-to-b`

### 禁止的模式
- 匹配 `^rounded-none`
- 匹配 `^shadow-(?!\[|none)`
- 匹配 `^bg-gradient-`
- 匹配 `^border-[248]`
- 匹配 `^bg-black`
- 匹配 `^bg-white$`

### 禁止原因
- `rounded-none`: Neumorphism requires rounded corners (rounded-xl or rounded-2xl)
- `shadow-lg`: Neumorphism uses dual-shadow system, not standard shadows
- `bg-white`: Neumorphism uses light gray backgrounds (#e0e5ec), not pure white
- `bg-black`: Neumorphism uses light gray backgrounds, not black
- `border-2`: Neumorphism avoids visible borders, shadows create separation
- `bg-gradient-to-r`: Neumorphism uses solid colors, no gradients

> WARNING: 如果你的代码中包含以上任何 class，必须立即替换。

---

## [REQUIRED] 必须包含

### 按钮必须包含
```
bg-[#e0e5ec]
rounded-xl
shadow-[6px_6px_12px_#b8bcc2,-6px_-6px_12px_#ffffff]
hover:shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff]
active:shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff]
transition-all duration-200
```

### 卡片必须包含
```
bg-[#e0e5ec]
rounded-2xl
shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]
```

### 输入框必须包含
```
bg-[#e0e5ec]
rounded-xl
shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff]
focus:shadow-[inset_6px_6px_12px_#b8bcc2,inset_-6px_-6px_12px_#ffffff]
focus:outline-none
placeholder:text-gray-400
transition-shadow duration-200
```

---

## [COMPARE] Neumorphism 错误 vs 正确对比

以下错误示例只代表“未经过当前风格适配的通用默认值”，不要把错误示例当成视觉建议。

### 按钮

[WRONG] **错误示例**（通用组件库默认样式，不要直接复制）：
```html
<button class="{GENERIC_LIBRARY_BUTTON_DEFAULT}">
  点击我
</button>
```

[CORRECT] **正确示例**（使用当前风格的 token）：
```html
<button class="bg-[#e0e5ec] rounded-xl shadow-[6px_6px_12px_#b8bcc2,-6px_-6px_12px_#ffffff] hover:shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff] active:shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] transition-all duration-200 bg-[#6d5dfc] text-white">
  点击我
</button>
```

### 卡片

[WRONG] **错误示例**（未经当前风格适配的通用卡片）：
```html
<div class="{GENERIC_LIBRARY_CARD_DEFAULT}">
  <h3>{TITLE}</h3>
</div>
```

[CORRECT] **正确示例**（使用当前风格的 card token）：
```html
<div class="bg-[#e0e5ec] rounded-2xl shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff] p-6 md:p-8">
  <h3 class="font-semibold text-gray-800 text-xl md:text-2xl">{TITLE}</h3>
</div>
```

### 输入框

[WRONG] **错误示例**（未经当前风格适配的通用输入框）：
```html
<input class="{GENERIC_LIBRARY_INPUT_DEFAULT}" />
```

[CORRECT] **正确示例**（使用当前风格的 input token）：
```html
<input class="bg-[#e0e5ec] rounded-xl shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] focus:shadow-[inset_6px_6px_12px_#b8bcc2,inset_-6px_-6px_12px_#ffffff] focus:outline-none placeholder:text-gray-400 transition-shadow duration-200" placeholder="{PLACEHOLDER}" />
```

---

## [TEMPLATES] Neumorphism 页面骨架模板

以下骨架只使用当前风格的 token。替换 `{PLACEHOLDER}` 时，不要移除或替换这些 token：

### 导航栏骨架
```html
<nav class="bg-[#e0e5ec] text-gray-800 border-0 border-transparent px-6 md:px-8">
  <div class="flex items-center justify-between max-w-6xl mx-auto gap-4 md:gap-6">
    <a href="/" class="font-semibold text-gray-800 text-xl md:text-2xl">
      {LOGO_TEXT}
    </a>
    <div class="flex gap-4 md:gap-6 text-gray-600 text-xs">
      {NAV_LINKS}
    </div>
  </div>
</nav>
```

### Hero 区块骨架
```html
<section class="bg-[#6d5dfc] text-gray-800 py-12 md:py-20 px-6 md:px-8">
  <div class="max-w-4xl mx-auto">
    <h1 class="font-semibold text-gray-800 text-4xl md:text-6xl">
      {HEADLINE}
    </h1>
    <p class="text-gray-600 text-sm md:text-base max-w-xl">
      {SUBHEADLINE}
    </p>
    <button class="bg-[#e0e5ec] rounded-xl shadow-[6px_6px_12px_#b8bcc2,-6px_-6px_12px_#ffffff] hover:shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff] active:shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] transition-all duration-200 bg-[#6d5dfc] text-white">
      {CTA_TEXT}
    </button>
  </div>
</section>
```

### 卡片网格骨架
```html
<section class="bg-[#e0e5ec] text-gray-800 py-12 md:py-20 px-6 md:px-8">
  <div class="max-w-6xl mx-auto">
    <h2 class="font-semibold text-gray-800 text-2xl md:text-3xl">{SECTION_TITLE}</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
      <!-- Card template - repeat for each card -->
      <div class="bg-[#e0e5ec] rounded-2xl shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff] p-6 md:p-8">
        <h3 class="font-semibold text-gray-800 text-xl md:text-2xl">{CARD_TITLE}</h3>
        <p class="text-gray-600 text-sm md:text-base text-gray-400">{CARD_DESCRIPTION}</p>
      </div>
    </div>
  </div>
</section>
```

### 表单输入骨架
```html
<input class="bg-[#e0e5ec] rounded-xl shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] focus:shadow-[inset_6px_6px_12px_#b8bcc2,inset_-6px_-6px_12px_#ffffff] focus:outline-none placeholder:text-gray-400 transition-shadow duration-200" placeholder="{PLACEHOLDER}" />
```

### 页脚骨架
```html
<footer class="bg-[#f0f0f3] text-gray-600 py-12 md:py-20 px-6 md:px-8">
  <div class="max-w-6xl mx-auto">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
      <div>
        <span class="font-semibold text-gray-800 text-xl md:text-2xl">{LOGO_TEXT}</span>
        <p class="text-gray-600 text-xs">{TAGLINE}</p>
      </div>
      <div>
        <h4 class="font-semibold text-gray-800 text-xl md:text-2xl">{COLUMN_TITLE}</h4>
        <ul class="text-gray-600 text-xs">
          {FOOTER_LINKS}
        </ul>
      </div>
    </div>
  </div>
</footer>
```

---

## [CHECKLIST] Neumorphism 生成后自检清单

**输出代码前，逐项验证当前风格的 token 和规则。如有违反，先修正再交付：**

### Token 检查
- [ ] 按钮包含： `bg-[#e0e5ec] rounded-xl shadow-[6px_6px_12px_#b8bcc2,-6px_-6px_12px_#ffffff] hover:shadow-[4px_4px_8px_#b8bcc2,-4px_-4px_8px_#ffffff] active:shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] transition-all duration-200`
- [ ] 卡片包含： `bg-[#e0e5ec] rounded-2xl shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]`
- [ ] 输入框包含： `bg-[#e0e5ec] rounded-xl shadow-[inset_4px_4px_8px_#b8bcc2,inset_-4px_-4px_8px_#ffffff] focus:shadow-[inset_6px_6px_12px_#b8bcc2,inset_-6px_-6px_12px_#ffffff] focus:outline-none placeholder:text-gray-400 transition-shadow duration-200`

### 禁止项检查
- [ ] 没有使用 `rounded-none`
- [ ] 没有使用 `rounded-sm`
- [ ] 没有使用 `shadow-sm`
- [ ] 没有使用 `shadow`
- [ ] 没有使用 `shadow-md`
- [ ] 没有使用 `shadow-lg`
- [ ] 没有使用 `shadow-xl`
- [ ] 没有使用 `shadow-2xl`

### 风格规则检查
- [ ] 使用浅色背景 bg-[#e0e5ec] 或 bg-[#f0f0f3]
- [ ] 使用双重阴影 shadow-[8px_8px_16px_#b8bcc2,-8px_-8px_16px_#ffffff]
- [ ] 凹陷效果使用 inset 阴影 shadow-[inset_8px_8px_16px_#b8bcc2,inset_-8px_-8px_16px_#ffffff]
- [ ] 使用中等圆角 rounded-xl (12-24px)
- [ ] 交互元素按下时从凸起变凹陷

### 风格漂移检查
- [ ] 没有违反：禁止使用纯黑或纯白背景
- [ ] 没有违反：禁止使用高对比度配色
- [ ] 没有违反：禁止使用粗边框 border-2 及以上
- [ ] 没有违反：禁止使用渐变背景 bg-gradient-*
- [ ] 没有违反：禁止直角 rounded-none

### 通用交付检查
- [ ] 响应式布局在手机、平板和桌面下稳定，没有横向溢出
- [ ] 所有交互元素有清晰焦点、可访问名称和 reduced-motion 方案
- [ ] 文本对比度达到 WCAG AA，且没有用颜色单独传递状态
- [ ] 结果仍然能够一眼识别为 Neumorphism

---

## [EXAMPLES] 示例 Prompt

### 1. 智能家居控制面板

设备控制和状态展示

```
用 Neumorphism 风格设计一个智能家居控制面板，要求：
1. 背景：统一浅灰色 #e0e5ec
2. 设备卡片：凸起效果，显示设备图标和状态
3. 开关按钮：圆形，开启时凹陷 + 强调色图标
4. 温度滑块：凹槽轨道，凸起滑块
5. 场景按钮：按下时从凸起变凹陷
所有阴影使用双色：右下深色 + 左上亮色
```

### 2. 计算器应用

拟物风格计算器界面

```
用 Neumorphism 风格创建一个计算器界面，要求：
1. 外框：大圆角凸起容器
2. 显示屏：凹陷区域，深色背景，显示数字
3. 数字按钮：4x3 网格，凸起效果
4. 运算符：右侧一列，用强调色
5. 按下效果：从凸起变凹陷
背景色 #e0e5ec，阴影用 #a3b1c6 和 #ffffff
```

### 3. 音频控制器

音量和均衡器控制

```
用 Neumorphism 风格设计一个音频控制器，要求：
1. 主容器：大圆角凸起面板
2. 旋钮：圆形凸起，带刻度指示
3. 推子/滑块：垂直凹槽，凸起滑块
4. 均衡器：多个垂直滑块并排
5. 按钮：静音/预设等，按下时凹陷
保持统一的浅灰色调，通过阴影创造立体感
```

## 绝对禁止（匹配即拒绝）

以下模式一旦出现，视为风格违规——不找借口，直接重写。

- 使用纯黑或纯白背景
- 使用高对比度配色
- 使用粗边框 border-2 及以上
- 使用渐变背景 bg-gradient-*
- 直角 rounded-none
- 按钮使用任何 translate 位移（新拟物元素是长在背景上的，不可浮起）
- hover 时增大阴影（与光影物理规律相悖，手指靠近应使阴影缩小）
- 打破光源方向（亮阴影必须在左上 -X/-Y，暗阴影必须在右下 +X/+Y）

## 自检清单（交付前逐条确认）

如果任何一条不通过，说明风格漂移了——修改后再交付。

- [ ] 没有紫色到蓝色的渐变
- [ ] 没有使用 Inter / Roboto / Geist 等过度使用的字体
- [ ] 没有嵌套卡片（卡片里面套卡片）
- [ ] 没有在彩色背景上放灰色文字
- [ ] 正文对比度满足 WCAG AA（≥4.5:1）
- [ ] 没有 bounce / elastic 缓动曲线
- [ ] 动效有 prefers-reduced-motion 备选方案
- [ ] 正文行宽不超过 65-75 个字符
- [ ] 没有单侧粗边框装饰（border-left/right accent stripe）
- [ ] 没有渐变文字（background-clip: text）
- [ ] 没有把玻璃态（glassmorphism）当作默认风格
- [ ] 没有 tiny uppercase tracked eyebrow 放在每个 section 标题上面
- [ ] 禁止使用纯黑或纯白背景
- [ ] 禁止使用高对比度配色
- [ ] 禁止使用粗边框 border-2 及以上
- [ ] 禁止使用渐变背景 bg-gradient-*
- [ ] 禁止直角 rounded-none