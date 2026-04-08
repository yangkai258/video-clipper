# Video Clipper DESIGN.md

> 智能视频切片工具视觉设计规范  
> 灵感来源：Vercel × Notion × Linear 的现代简洁风格  
> 更新时间：2026-04-08

---

## 🎨 设计原则

**1. 功能优先** - 视频编辑工具，效率第一  
**2. 清晰层次** - 状态、进度、操作一目了然  
**3. 冷静专业** - 避免花哨，专注内容  
**4. 一致性** - 所有页面遵循同一套设计语言

---

## 🎨 色彩系统

### 主色

```css
--primary: #0070f3;        /* Vercel 蓝 - 主要操作按钮 */
--primary-hover: #0060df;  /* 悬停状态 */
```

### 状态色

```css
--success: #00a94f;        /* 完成、成功状态 */
--warning: #f5a623;        /* 警告、处理中 */
--danger: #e00;            /* 删除、错误 */
--info: #0070f3;           /* 信息提示 */
```

### 中性色

```css
--bg: #ffffff;             /* 背景 */
--bg-secondary: #f7f7f7;   /* 次要背景（卡片、上传区） */
--border: #eaeaea;         /* 边框 */
--text: #000000;           /* 主要文字 */
--text-secondary: #666666; /* 次要文字 */
--text-tertiary: #999999;  /* 提示文字 */
```

### 版本标识色

```css
--release: #10b981;        /* 正式版 - 绿色 */
--beta: #f59e0b;           /* 测试版 - 橙色 */
```

---

## 📐 间距系统

**基础单位：** `8px`

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 16px;
--space-4: 24px;
--space-5: 32px;
--space-6: 48px;
```

**使用规则：**
- 卡片内边距：`24px`
- 卡片间距：`16px`
- 页面边距：`32px`
- 元素间距：`8px` 或 `16px`

---

## 🔤 字体系统

### 字体栈

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
```

### 字号

```css
--text-xs: 12px;           /* 标签、提示 */
--text-sm: 14px;           /* 次要文字 */
--text-base: 16px;         /* 正文 */
--text-lg: 18px;           /* 小标题 */
--text-xl: 24px;           /* 页面标题 */
--text-2xl: 32px;          /* 大标题 */
```

### 字重

```css
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

---

## 🧩 组件规范

### 按钮

```css
/* 主要按钮 */
.btn-primary {
  background: var(--primary);
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-primary:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

/* 次要按钮 */
.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text);
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  border: 1px solid var(--border);
  cursor: pointer;
}

/* 危险按钮 */
.btn-danger {
  background: var(--danger);
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  border: none;
  cursor: pointer;
}
```

### 卡片

```css
.card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
```

### 上传区域

```css
.upload-zone {
  border: 2px dashed var(--border);
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  background: var(--bg-secondary);
  transition: all 0.2s;
}
.upload-zone:hover {
  border-color: var(--primary);
  background: rgba(0, 112, 243, 0.05);
}
```

### 进度条

```css
.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 4px;
  transition: width 0.3s;
}
```

### 状态标签

```css
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}
.status-pending {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}
.status-processing {
  background: rgba(245, 166, 35, 0.1);
  color: var(--warning);
}
.status-completed {
  background: rgba(0, 169, 79, 0.1);
  color: var(--success);
}
.status-error {
  background: rgba(230, 0, 0, 0.1);
  color: var(--danger);
}
```

### 版本标识

```css
.version-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 16px;
}
.version-release {
  background: rgba(16, 185, 129, 0.1);
  color: var(--release);
}
.version-beta {
  background: rgba(245, 158, 11, 0.1);
  color: var(--beta);
}
```

---

## 📱 布局规范

### 页面容器

```css
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 24px;
}
```

### 网格布局

```css
/* 项目列表 - 响应式网格 */
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 16px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .project-grid {
    grid-template-columns: 1fr;
  }
  .container {
    padding: 16px;
  }
}
```

---

## 🎬 页面特定规范

### 首页（项目列表）

**结构：**

```
版本标识
页面标题
├─ 上传区域
└─ 项目列表
   ├─ 项目卡片
   │  ├─ 项目名称 + 状态标签
   │  ├─ 进度条
   │  ├─ 统计信息（切片数、合集数）
   │  └─ 操作按钮（查看、删除）
```

### 项目详情页

**结构：**

```
返回按钮 + 页面标题
├─ 项目信息卡片
│  ├─ 视频预览
│  ├─ 基本信息（时长、状态、创建时间）
│  └─ 处理进度
├─ 切片列表
│  └─ 切片卡片（缩略图 + 时间戳 + 分数）
└─ 合集列表
   └─ 合集卡片（标题 + 包含切片数）
```

---

## 🎭 交互规范

### 悬停效果

```css
/* 卡片悬停 */
.card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  transform: translateY(-2px);
  transition: all 0.2s;
}

/* 按钮悬停 */
button:hover {
  transform: translateY(-1px);
  transition: all 0.2s;
}
```

### 加载状态

```css
/* 骨架屏 */
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
}
@keyframes loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### 动画

```css
/* 淡入 */
.fade-in {
  animation: fadeIn 0.3s ease-in;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
```

---

## 📊 数据可视化

### 进度显示

```
[进度条] 45%
当前步骤：生成字幕中...
预计剩余：约 8-12 分钟
```

### 统计信息

```
📹 159 个切片  📁 20 个合集  ⏱️ 2:13:15
```

---

## 🎨 暗黑模式（未来扩展）

```css
@media (prefers-color-scheme: dark) {
  --bg: #1a1a1a;
  --bg-secondary: #2a2a2a;
  --border: #3a3a3a;
  --text: #ffffff;
  --text-secondary: #aaaaaa;
}
```

---

## 📝 文案规范

### 按钮文案

- ✅ "开始处理"、"查看详情"、"删除"
- ❌ "点击这里"、"点我"

### 状态文案

- ✅ "处理中"、"已完成"、"等待中"
- ❌ "正在搞"、"好了"、"没动"

### 错误提示

- ✅ "处理失败：视频格式不支持"
- ❌ "出错了"、"挂了"

---

## 🔗 参考灵感

- **Vercel** - 简洁的蓝白配色、清晰的层次
- **Notion** - 卡片式布局、柔和的阴影
- **Linear** - 状态标签、进度展示
- **Stripe** - 专业的工具感、细腻的微交互

---

**最后更新：** 2026-04-08  
**维护者：** 剪辑小助理 ✂️
