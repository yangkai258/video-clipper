# v2.1 UI 升级：毛玻璃 + 亮暗切换

**日期**：2026-06-28
**状态**：设计已批准，等待实施

## 背景

video-clipper v2.0 已上线纯深色 Linear 风格 UI。本次升级聚焦在视觉与可达性：

1. **毛玻璃效果** — 整体 UI 升级为强毛玻璃风格（macOS Sonoma / Apple Vision Pro 范式）
2. **亮暗切换** — 用户可在顶栏一键切换主题，满足不同时段使用习惯
3. **多用户支持** — LAN 部署多台电脑访问，每台电脑浏览器独立 localStorage 天然隔离

## 决策汇总

| 维度 | 选择 | 理由 |
|------|------|------|
| 毛玻璃强度 | **C 强** | 用户明确要求"融合毛玻璃"，强档视觉冲击最强 |
| 渐变背景色 | **B 暖橙夕阳** `#fb923c → #ec4899 → #06b6d4` | 暖色有人情味，青尾巴提亮，符合视频创作工具属性。**用户明确拒绝紫色** |
| 切换入口 | **A 顶栏按钮** ☀/🌙 | 最直观、最快。顶栏右侧，搜索框旁 |
| 主题存储 | **A localStorage** | 多台电脑 LAN 访问，浏览器级天然隔离，零工程量 |

## 目标

- ✅ 整体 UI 升级为毛玻璃风格（chrome + 卡片 + modal）
- ✅ 背景换彩色渐变（无紫色系）
- ✅ 顶栏一键切换亮 / 暗
- ✅ localStorage 持久化，刷新页面保留
- ✅ 不引入性能负担（低端 Mac 仍流畅）
- ✅ 不破坏现有 pytest 套件（32 项全过）

## 非目标（YAGNI）

- ❌ 后端 user_preferences 同步（localStorage 已足够 LAN 多用户场景）
- ❌ 跟随系统主题（用户没要求，避免 first-time UX 复杂）
- ❌ 自定义主色调（每用户可改背景色）
- ❌ 主题切换过渡曲线精细调优（默认 ease 0.3s 已够）
- ❌ WatchFolder / ProjectDetail 等子页面单独主题（继承全局）

## 架构

### 数据流

```
浏览器启动
  ↓
App.jsx useEffect 读 localStorage.theme (默认 'dark')
  ↓
document.documentElement.dataset.theme = 'dark' | 'light'
  ↓
CSS 变量切换（瞬时，无 JS 重渲染）
  ↓
ThemeToggle 按钮点击
  ↓
toggleTheme() → 切换 dataset + 写 localStorage
```

### 组件改动（3 个文件 + 1 个新文件）

```
frontend/src/index.css        [修改] 把 :root 重命名为 :root[data-theme="dark"]
                                  新增 :root[data-theme="light"] 浅色版
                                  所有面板加 transition
frontend/src/App.jsx          [修改] useEffect 初始化 theme
                                  新增 <ThemeToggle /> 在 topbar
frontend/src/ThemeToggle.jsx  [新增] ~30 行按钮组件
frontend/src/main.jsx         [无需改动] React 入口
```

## 设计细节

### 1. CSS 变量（index.css）

**深色（保留现有 + 微调）**：
```css
:root[data-theme="dark"] {
  --bg-base: #0d0e12;
  --bg-elevated: #131419;
  --bg-card: rgba(22, 24, 31, 0.6);     /* 卡片半透明 */
  --bg-glass: rgba(19, 20, 25, 0.55);    /* 毛玻璃底 */
  --text-bright: #e8e8ed;
  --text-muted: #6b6f7d;
  --text-faint: #4a4d57;
  --border: rgba(255, 255, 255, 0.06);
  --border-strong: rgba(255, 255, 255, 0.12);
  --accent: #5e6ad2;
  --bg-gradient: linear-gradient(135deg, #fb923c 0%, #ec4899 50%, #06b6d4 100%);
  --blur-strength: 24px;
  --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

**浅色（新增）**：
```css
:root[data-theme="light"] {
  --bg-base: #f5f5f7;                      /* macOS 标准浅灰 */
  --bg-elevated: rgba(255, 255, 255, 0.85); /* 半透明白 */
  --bg-card: rgba(255, 255, 255, 0.65);
  --bg-glass: rgba(255, 255, 255, 0.55);
  --text-bright: #1a1a1f;
  --text-muted: #6b6f7d;
  --text-faint: #a0a3ab;
  --border: rgba(0, 0, 0, 0.08);
  --border-strong: rgba(0, 0, 0, 0.15);
  --accent: #ea580c;                       /* 暖橙 accent（浅色背景适配） */
  --bg-gradient: linear-gradient(135deg, #fb923c 0%, #ec4899 50%, #06b6d4 100%);
  --blur-strength: 24px;
  --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

**全屏背景**：所有页面 body 加 `background: var(--bg-gradient); background-attachment: fixed;`

### 2. 毛玻璃面板（统一规则）

所有 chrome / 卡片 / modal / 顶栏 / 侧边栏：
```css
.panel {
  background: var(--bg-glass);
  backdrop-filter: blur(var(--blur-strength)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--blur-strength)) saturate(180%);
  border: 1px solid var(--border);
  transition: var(--transition);
}
```

### 3. ThemeToggle 组件

```jsx
// frontend/src/ThemeToggle.jsx
import { useEffect, useState } from 'react'

export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => 
    localStorage.getItem('theme') || 'dark'
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggle = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  return (
    <button
      className="theme-toggle"
      onClick={toggle}
      aria-label={`切换到${theme === 'dark' ? '亮色' : '暗色'}主题`}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  )
}
```

```css
.theme-toggle {
  background: var(--bg-glass);
  backdrop-filter: blur(var(--blur-strength));
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 14px;
  cursor: pointer;
  transition: var(--transition);
}
.theme-toggle:hover {
  background: var(--bg-card);
  transform: scale(1.05);
}
```

### 4. App.jsx 集成点

```jsx
// 1. 顶部 import
import ThemeToggle from './ThemeToggle'

// 2. 在 topbar 渲染（搜索框后、新建切片按钮前）
<input className="search-input" ... />
<ThemeToggle />
<label className="btn btn-primary upload-compact">...</label>
```

### 5. 现有元素改造映射

| 元素 | 改造 |
|------|------|
| `.sidebar` | 加 `background: var(--bg-glass); backdrop-filter: blur(...)` |
| `.reel-row` | 加毛玻璃背景 |
| `.modal` | 加毛玻璃 + 加深阴影 |
| `.topbar` | 加毛玻璃 |
| `.btn-primary` | 浅色主题下用 `#ea580c` 暖橙 |
| `body` | 加 `var(--bg-gradient)` 全屏渐变 |

## 测试

### pytest 新增（4 项）

```python
# tests/test_ui_theme.py

def test_index_css_has_dark_theme():
    """验证 :root[data-theme="dark"] 存在"""
    css = open('frontend/src/index.css').read()
    assert ':root[data-theme="dark"]' in css

def test_index_css_has_light_theme():
    """验证 :root[data-theme="light"] 存在"""
    css = open('frontend/src/index.css').read()
    assert ':root[data-theme="light"]' in css

def test_gradient_has_no_purple():
    """验证渐变背景不含紫色 (hue 270-290°)"""
    css = open('frontend/src/index.css').read()
    # 提取 gradient 行
    gradient_lines = [l for l in css.split('\n') if 'linear-gradient' in l and '#' in l]
    for line in gradient_lines:
        # 紫色 hex: 270-290° hue 范围大致 #6b21a8 到 #a855f7
        for hex_code in ['#8b5cf6', '#a855f7', '#7c3aed', '#6b21a8', '#5b21b6']:
            assert hex_code not in line.lower(), f"紫色 {hex_code} 出现在 gradient 中"

def test_theme_toggle_file_exists():
    """验证 ThemeToggle.jsx 已创建"""
    assert os.path.exists('frontend/src/ThemeToggle.jsx')
```

### 端到端手动验证

1. 打开 `http://localhost:3030`
2. 检查：整体毛玻璃、暖橙渐变背景、紫色已无
3. 点击顶栏 ☀ 按钮 → 主题切换为亮色，毛玻璃保持半透明白
4. 刷新页面 → 主题保留（localStorage）
5. 切到 Safari / Chrome 比较 → 各自独立（不串）

## 风险

| 风险 | 缓解 |
|------|------|
| `backdrop-filter` 在低端 GPU 卡 | Mac Sonoma+ / 2019+ Mac 都支持；老机器会自动 fallback 到实色 |
| 浅色主题文字对比度不足 | 浅色用 `#1a1a1f` on `#f5f5f7` → contrast 16:1（远超 WCAG AAA 7:1） |
| 用户偏好冲突（多人同一浏览器） | 当前无登录系统，按"每浏览器独立"处理 |
| 切换闪烁 | CSS 变量切换是瞬时（无 JS 重渲染）；transition 加在 panel 上 |

## 文件改动清单

| 文件 | 改动 |
|------|------|
| `frontend/src/index.css` | 大改：变量重命名 + 新增 light 变量 + 毛玻璃 transition |
| `frontend/src/App.jsx` | 小改：import ThemeToggle + topbar 渲染 |
| `frontend/src/ThemeToggle.jsx` | 新增：~30 行 |
| `tests/test_ui_theme.py` | 新增：4 项测试 |
| `docs/superpowers/specs/2026-06-28-glass-theme-design.md` | 本文档 |

总计：1 新增大文件 + 1 新增小文件 + 1 新增测试 + 2 修改 = ~250 行

## 实施顺序

1. 写 index.css 变量 + 毛玻璃 transition（约 60% 工作量）
2. 写 ThemeToggle.jsx + App.jsx 集成（约 20%）
3. 写 4 项 pytest（约 10%）
4. 手动端到端验证（约 10%）

## 验收标准

- [ ] `pytest tests/ -v` 全过（原 32 + 新 4 = 36 项）
- [ ] 浏览器目视：毛玻璃 ✓ 暖橙渐变 ✓ 无紫 ✓ 切换流畅 ✓
- [ ] localStorage 持久化 ✓
- [ ] 多浏览器独立 ✓
- [ ] 浅色主题文字对比度 ≥ 7:1
- [ ] watch folder / projects / style manager / project detail 4 个页面都生效
- [ ] 性能：无明显卡顿（拖动 / 滚动 / 切换）

## 不在本设计内（后续可考虑）

- 主题切换时的微妙过渡动画（cross-fade）
- 自定义 accent 颜色（每用户选主色）
- 跟随系统主题（prefers-color-scheme）
- 后端持久化偏好（需要登录系统）
- 主题切换快捷键（Cmd+Shift+L）

---

🤖 Generated with brainstorming skill workflow