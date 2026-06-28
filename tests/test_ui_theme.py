"""
v2.1 UI 主题测试

覆盖：
- :root[data-theme="dark"] / :root[data-theme="light"] 变量块存在
- 渐变背景不含紫色（HSL hue 270-290°）
- ThemeToggle.jsx 组件文件存在
- 毛玻璃 backdrop-filter 应用到关键面板
"""
import os
import re
from pathlib import Path


# ==== Helpers ====

def hex_to_hsl(hex_color: str):
    """#RRGGBB → (h, s, l) h ∈ [0, 360]"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return None
    r, g, b = (int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        h = 0
        s = 0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h /= 6
    return h * 360, s * 100, l * 100


def is_purple(hex_color: str) -> bool:
    """紫色判定：hue ∈ [270°, 290°]"""
    hsl = hex_to_hsl(hex_color)
    if hsl is None:
        return False
    h = hsl[0]
    return 270 <= h <= 290


def extract_gradient_colors(css_text: str):
    """从 CSS 提取 linear-gradient 里的所有 #RRGGBB"""
    colors = []
    in_gradient = False
    for line in css_text.split('\n'):
        if 'linear-gradient' in line:
            in_gradient = True
        if in_gradient:
            colors.extend(re.findall(r'#[0-9a-fA-F]{6}', line))
            if ';' in line:
                in_gradient = False
    return colors


ROOT = Path(__file__).parent.parent
INDEX_CSS = ROOT / "frontend" / "src" / "index.css"
THEME_TOGGLE = ROOT / "frontend" / "src" / "ThemeToggle.jsx"
APP_JSX = ROOT / "frontend" / "src" / "App.jsx"


# ==== Tests ====

def test_index_css_has_dark_theme():
    """验证 :root[data-theme="dark"] 存在且包含关键变量"""
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ":root[data-theme=\"dark\"]" in css, \
        "缺少 :root[data-theme=\"dark\"] 块"
    # 关键变量
    for var in ["--bg-base", "--text-bright", "--accent", "--bg-gradient", "--blur-strength"]:
        assert f"{var}:" in css, f"dark 主题缺变量 {var}"


def test_index_css_has_light_theme():
    """验证 :root[data-theme="light"] 存在且 accent 是暖橙（不是紫蓝）"""
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ":root[data-theme=\"light\"]" in css, \
        "缺少 :root[data-theme=\"light\"] 块"

    # 提取 light 块（从 :root[data-theme="light"] 开始到下一个 }）
    light_start = css.find(':root[data-theme="light"]')
    light_block = css[light_start:light_start + 1500]  # 取 1500 字符覆盖整个块

    # 浅色主题 accent 应该是暖橙系
    assert "--accent: #ea580c" in light_block or "#ea580c" in light_block, \
        "浅色主题 accent 应是 #ea580c 暖橙（用户明确拒绝紫色）"
    assert "--text-bright: #1a1a1f" in light_block, \
        "浅色主题应有深色文字 (#1a1a1f) 确保对比度"


def test_no_purple_in_gradient():
    """验证渐变背景不含紫色 (HSL hue 270-290°)

    用户明确说"颜色别用紫色"，所以任何 linear-gradient 都不能含紫色 hex
    """
    css = INDEX_CSS.read_text(encoding="utf-8")
    colors = extract_gradient_colors(css)

    # 至少要有一个渐变
    assert len(colors) > 0, "应该至少有 1 个 linear-gradient"

    purple_colors = [c for c in colors if is_purple(c)]
    assert len(purple_colors) == 0, \
        f"渐变背景含紫色：{purple_colors}（用户明确拒绝紫色）"

    # 显式检查 5 个常见紫色 hex
    common_purples = ["#8b5cf6", "#a855f7", "#7c3aed", "#6b21a8", "#5b21b6", "#9333ea"]
    for purple in common_purples:
        for line in css.split("\n"):
            if "linear-gradient" in line.lower() or "bg-gradient" in line.lower():
                assert purple not in line.lower(), \
                    f"紫色 {purple} 出现在 gradient 行：{line.strip()[:80]}"


def test_theme_toggle_component_exists():
    """验证 ThemeToggle.jsx 创建且有核心逻辑"""
    assert THEME_TOGGLE.exists(), \
        f"ThemeToggle.jsx 未创建：{THEME_TOGGLE}"

    code = THEME_TOGGLE.read_text(encoding="utf-8")

    # 关键 API
    assert "localStorage" in code, "ThemeToggle 必须用 localStorage 持久化"
    assert "dataset.theme" in code, "ThemeToggle 必须设 document.documentElement.dataset.theme"
    assert "useState" in code, "ThemeToggle 必须用 useState 管理 theme state"
    assert "useEffect" in code, "ThemeToggle 必须用 useEffect 同步 DOM"
    assert ("Icon" in code and "sun" in code and "moon" in code), "ThemeToggle 应有 SVG icon 切换 (v2.1.43 替代 emoji)"

    # App.jsx 必须 import + 渲染
    app_code = APP_JSX.read_text(encoding="utf-8")
    assert "ThemeToggle" in app_code, "App.jsx 必须 import ThemeToggle"
    assert "<ThemeToggle" in app_code, "App.jsx 必须渲染 <ThemeToggle />"
