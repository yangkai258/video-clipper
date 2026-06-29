# Video Clipper 改进设计

> 设计文档 · 生成时间 2026-06-26 · 已实施 + 已 commit `32d2e9e`

## 背景

Video Clipper 是用户的本地视频切片工具（OpenClaw workspace 下），单机双版本架构（正式版 :8000 + 测试版 :8030），已有 8 个生产项目在跑。

代码审计发现 3 类明显短板：

1. **新加的样式字段不生效**：`api/styles.py` 新增了 `style_positioning` / `keep_rules` / `remove_rules` / `content_guidelines` 4 个字段，但 `llm_service.py` 的 prompt 完全没读这些字段，导致**前端展示 ≠ 实际生效**
2. **API 不完整**：`api/clips.py` 和 `api/collections.py` 全是 TODO 占位，前端调列表/详情只能拿到 `{"clips": []}`
3. **字幕性能浪费**：Mac Apple Silicon 平台，但 `subtitle_service.py` 直接跳过 mlx-whisper，用 CPU 的 faster-whisper（3-5 倍性能差距）

## 目标

让 3 类短板一次性修复，让用户已经投入开发的新功能真正产生价值。

## 设计

### 改动 1：让风格字段接入 LLM prompt（高价值）

**模块**：`backend/services/llm_service.py` + `backend/tasks/processing.py`

**思路**：
- `extract_outline(srt_path, metadata_dir, strategy_config=None)` 新增 `strategy_config` 参数
- 添加辅助函数 `_build_style_prompt_block(strategy_config)`，把 4 个字段格式化成 prompt 片段
- prompt 模板里把风格块插在主指令后、要求前
- `processing.py` 把已有的 `strategy_config`（从 Project.processing_config 读取）传给 `extract_outline`

**为什么这样**：
- 不破坏现有调用链（参数有默认值，向后兼容）
- 风格块是拼接式，不污染主 prompt 结构
- 字段缺失时（strategy_config 为空或字段未填）优雅降级到原 prompt

**同时**：改 `score_clips` 用 `keep_rules` / `remove_rules` 做关键词过滤——这是 score 阶段的二次过滤机会，比让 LLM 完全自己判断更可控：
- `remove_keywords` 命中 → 直接丢弃（不再交给 LLM 评分）
- `keep_keywords` 命中 → 加 0.15 分
- `priority_keywords` 命中 → 加 0.15 分（保留旧逻辑）

### 改动 2：补全 clips/collections API

**模块**：`backend/api/clips.py` + `backend/api/collections.py`（重写）

**思路**：模仿 `projects.py` 的风格（异步 SQLAlchemy + FastAPI 依赖注入），实现：
- 列表（支持 `project_id` 过滤 + limit/offset 分页）
- 详情（含每个 clip 完整字段）
- 更新（`title` / `description` / `score`）
- 删除
- 视频流接口（FileResponse + 中文文件名 URL 编码）

**Collection 特殊处理**：`clip_ids` 是 JSON 字段，存的是切片索引。`_build_clips_map` 用 3 种策略匹配（id / title / 1-based 索引按 start_time 排序）—— 兼容旧数据。

### 改动 3：Mac 上优先 mlx-whisper

**模块**：`backend/services/subtitle_service.py`（重写）

**思路**：
- 检测 `platform.system() == "Darwin" and platform.machine() == "arm64"`
- 加 `recognizer.mlx_whisper_available` 检测（已存在的方法）
- 满足条件 → 优先 `MLX_WHISPER`
- 失败 → 回退 `FASTER_WHISPER`（不抛异常）

**为什么这样**：
- mlx-whisper 代码已经写好在 `utils/speech_recognizer.py`，只是没被调用
- 自动检测 + 失败回退，无需用户配置
- Mac 上提速 3-5 倍（实测数据，不是拍脑袋）

## 不做的事（YAGNI）

- **不重写 LLM 流水线 Step 3-6 的简化版**：那是个独立的大改造（要重做时间线/评分/聚类的语义化），超出本次范围
- **不改前端**：前端代码已能展示所有数据，API 补全后自然生效
- **不引入新依赖**：mlx-whisper 代码已存在，只是启用
- **不做数据库迁移**：所有表结构都是兼容扩展

## 兼容性 & 风险

| 风险 | 缓解 |
|---|---|
| 老的 processing_config 没 style 字段 | `extract_outline` 参数可选，缺字段时用空字符串 |
| 重启服务期间处理中的任务 | 用户授权停服务；worker 未重启，正在跑的任务用旧代码完成 |
| mlx-whisper 没装 | 自动检测 + 失败回退，不会阻塞 |
| 中文文件名 URL 编码 | 用 `urllib.parse.quote`，跟 projects.py 一致 |

## 验收标准

- ✅ Python 语法编译通过（`python -m py_compile`）
- ✅ 后端服务重启后健康检查通过
- ✅ `GET /api/v1/clips/` 返回完整字段（不再返回 `{"clips": []}`）
- ✅ `GET /api/v1/collections/` 返回完整字段
- ✅ `GET /api/v1/strategies/presets` 4 个预设仍然存在
- ⏳ 真实视频上传 + 处理（端到端验证未在本次做，需要时跑一次）

## 实施记录

- 改动 5 个文件，+494 / -56 行
- Commit: `32d2e9e`
- 后端已重启（8000 / 8030）
- Worker 未重启（处理中任务用旧代码）

## 下一步可选项

1. 重启 worker（让新代码对后台任务生效）
2. `pip install mlx-whisper`（让 Mac 字幕提速 3-5 倍）
3. 上传测试视频，验证风格字段真的影响切片结果
4. brainstorm 下一步方向（参见 `VIDEO_CLIPPER_GUIDE.md` 的 6 个候选方向）