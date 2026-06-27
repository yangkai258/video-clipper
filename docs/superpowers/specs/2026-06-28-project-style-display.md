# v2.1.2 项目列表显示风格

**日期**：2026-06-28
**状态**：实施中

## 背景

v2.1 项目列表只显示状态/创建时间/切片数，**不显示用了什么风格**。用户希望一眼看到每个项目用了什么 style。

## 目标

- ✅ 后端 `GET /api/v1/projects/` 返回 `style_id` + `style_name`
- ✅ 前端 `.reel-row` 加一列显示风格 badge
- ✅ 没选过风格的项目显示「默认」灰色 badge
- ✅ 不破坏现有 36 项测试

## 决策

| 维度 | 决定 |
|------|------|
| 字段 | `style_id` (string) + `style_name` (string) |
| 找不到 style | name='默认' + 灰色 badge |
| 计算位置 | 后端 `list_projects` / `get_project` 一次 join，避免 N+1 |
| UI 列宽 | 100px（容纳风格名） |
| Badge 颜色 | 深色紫蓝 accent / 浅色暖橙 accent；"默认"用灰 |

## 改动清单

| 文件 | 改动 |
|------|------|
| `backend/api/projects.py` | list/get 加 `_resolve_style()` helper 返回 `{style_id, style_name}` |
| `frontend/src/App.jsx` | `.reel-row` 渲染风格 badge |
| `frontend/src/index.css` | `.style-badge` 样式（深浅主题各一） |
| `tests/test_project_style.py` | 新增 2 项测试 |

## 不做（YAGNI）

- ❌ 风格筛选（按风格过滤项目）
- ❌ 风格切换（点 badge 改风格）
- ❌ 预设风格的图标/颜色区分

## 验收

- [ ] 36 + 2 = 38 项 pytest 全过
- [ ] 后端 `/projects/` 返回 style_id/style_name 字段
- [ ] 前端项目列表每行显示风格 badge
- [ ] 没选过风格显示「默认」灰色
- [ ] 截图通过

🤖 Generated with brainstorming skill workflow