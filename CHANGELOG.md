# Changelog

video-clipper 14 个最近版本 (v2.2.30 → v2.2.43) 的变更记录.
按时间倒序, 每版含: 改了什么 / 修的 bug / 测试覆盖 / commit + tag 链接.

---

## v2.2.43 — reset + redispatch mix script (2026-07-26)
**feat(tool)**: 一键重置老 mix project + 重派发, 验证 v2.2.42 round-robin 修.

- 新文件 `scripts/reset_and_redispatch_mix.py`:
  1. 找老 source_clip_id (3 unique from bc65f840)
  2. DELETE `mix_source_clips` + `mix_tasks` WHERE `mix_project_id=?`
  3. UPDATE `project.status=pending` + 清 `output_video_path/duration`
  4. DELETE 老 mp4 + thumbnail + `_extract_parts/`
  5. `dispatch_mix_task` 直接调 (不创建新 project, 保留老 id + 引用)
- E2E 验证 bc65f840: 重置前 7 段 fallback 同 1 clip, 重置后 5 段 5 不同 clip ✓
- 提 issue 14: 老 mix project 因 v2.2.26 fallback bug 重复, 不能手动修 (worker 不会清老 source_clips)

## v2.2.42 — fallback round-robin (2026-07-26)
**fix(mix)**: 修"选了多个视频但只有 1 个在循环" 的 bug.

- **Root cause** (user 报 14:32): v2.2.26/v2.2.36 fallback 路径永远用 `clip_library[0]`. 多个 segment 都 0 match 时, 7 段 fallback 全到同一 clip → 视觉上看 1 个视频循环.
- **修法**: fallback 改成 round-robin (`seg['position'] % len(clip_library)`), 每段选不同 clip.
- E2E 验证 8 段 8 候选: 8 source_clips title 全不同, status completed, mp4 60s.
- 新 test `test_多段_fallback_round_robin_v2_2_42`: 8 段 4 候选, 验证 round-robin 顺序 `[a,b,c,d,a,b,c,d]`.

## v2.2.41 — Step 2 按段预选 (2026-07-26)
**feat(mix)**: Step 2 wizard 加按段预选 UI + 自动勾选 top-1.

- 新 endpoint `POST /api/v1/mix/preview-match` 接 (segments, candidate_clip_ids, top_n=3, target_duration):
  - 调 `build_clip_library_from_slice_db` + substring tag overlap 公式
  - 返 `[{position, text, keywords, top_clips: [{clip_id, title, project_name, duration, match_score, matched_keywords}, ...]}]`
  - 不写 db, 纯计算
- 前端 Step 2 改: 调 `/preview-match` → 显示按段分组 (每段 header + top-3 缩略图) + 自动勾选 top-1
  - top-1 蓝色边框 + "top-1" 角标
  - 命中关键词标绿, 折叠/展开
- 新 CSS `.segment-preselect-*` 12 条样式 (暖色/海洋配色)
- 6 个新 test (`tests/test_preview_match.py`)

## v2.2.40 — 列表卡片快捷"存到资源库"按钮 (2026-07-26)
**feat(ui)**: User 反馈 list 页面看不到"加到资源库"按钮, 必须进 ProjectDetail.

- `ProjectCard.jsx` 加 `onSaveToLibrary` prop, completed + clip_count > 0 时显示
- `App.jsx` 加 `saveProjectToLibrary` handler, 调 `POST /library/from-project` 批量加
  - confirm 弹窗 + 结果 alert (新增/跳过/失败数) + 跳资源库提示
- CSS: `.reel-card-actions .btn-danger` flex 0 0 auto (避免 4 按钮挤压)
- 7 个新 vitest (`ProjectCard.test.jsx`): completed 显示 / pending 不显示 / failed 不显示 / 0 clip 不显示 / 点击触发 / stopPropagation / 老用法兼容

## v2.2.39 — embedding placeholder key skip (2026-07-26)
**fix(embed)**: 修"每次 e2e 跑 mix 报 100+ 条 'embedding API 调用失败: data' warning".

- **Root cause**: `OPENAI_API_KEY` 是 `sk-empty-f...test` placeholder (23 chars), 每次调都 401 (response 不是 JSON, `response.json()` 抛 `ValueError 'data'`)
- **修法**: `_call_embedding` 加 placeholder key 检测 (key 长度 < 30 OR 包含 `empty/placeholder/your-key/test-key/-test`) → 提前 return None + log debug
- 4 个新 test (`tests/test_embedding_placeholder.py`): placeholder skip / 真 key 走请求 / 短 key skip / 无 env skip
- 行为不变: 仍然 keyword-only match (v2.2.33 公式 0.7 tag + 0.3 embed, embed 失败 fallback keyword)

## v2.2.38 — 资源库封面兜底 + auto-tag 默认关闭 (2026-07-26)
**fix(library)**: User 反馈"资源库没封面图, 抽过来的规则不好用".

- `from-clip` 端点兜底: 源 thumbnail 复制失败/不存在时, 调 `_generate_thumbnail` (1s 帧 ffmpeg 抽)
- 3 处 auto-tag 触发 (upload / from-clip / from-project batch) 注释掉:
  - User 觉得 v2.2.19 LLM auto-tag 规则不准, 暂时关掉
  - 留 `_auto_tag_in_thread` 函数 + `POST /library/{id}/auto-tag` manual endpoint, 想用时手跑
- `from-clip` 顺便抽源 `clip_metadata.tags` (跟 v2.2.21 visual match 配套), 替换之前的硬编码 `tags=[]`
- 新脚本 `scripts/backfill_resource_thumbnails.py`: 跑 1 次给所有 thumbnail 缺失的 resource 重新 ffmpeg 抽
  - 实测: beta 81/81 ✓, release 75/79 (4 个 mp4 物理文件不存在 fail)
- 6 个新 test (`tests/test_library_thumbnail.py`)

## v2.2.37 — 跨 release/beta 模式混剪 (2026-07-26)
**fix(mix)**: User 报"13:19 跑混剪, detail page 来源片段 0 条" + 失败.

- **Root cause** (v2.2.5 遗留, 漂 11 个月):
  1. `mix_dispatch.dispatch_mix_task` hardcode `db=0/processing_mix`
  2. beta uvicorn (db=1) 派发到 db=0/processing_mix
  3. mix worker 用 release DATABASE_URL 查 release 切片 db, 找不到 beta 资源库 ID
  4. 0 source clips, raise RuntimeError, project.status=failed, `mix_source_clips` 表 0 行
  5. detail page `source_clips.length === 0` 显示"暂无" → user 困惑
- **修法** (完整 3 块):
  1. `mix_dispatch` 跟 uvicorn 模式走: 读 `CELERY_BROKER_URL` env 决定 broker db, queue 按 broker db 推 (db 0 → processing_mix, db 1 → processing_mix_beta)
  2. `check_workers.sh start_mix_worker` 启 **2 个** mix worker (release 走 release db + db 0 / processing_mix, beta 走 beta db + db 1 / processing_mix_beta)
  3. Test: `_resolve_mix_dispatch_broker/queue` 每次调用读 env, 不依赖模块常量 cache (避免 reload 模块污染其他 test)
- 5 个新 test (`tests/test_mix_dispatch.py` 改 + `tests/test_mix_dispatch_env.py` 新)

## v2.2.36 — substring 匹配 + batch sync 资源库脚本 (2026-07-26)
**fix(mix)**: tag overlap 严格相等 0 match 触发 RuntimeError.

- **修法**: `match_clips_for_segments` 加 substring 命中 (`kw == ct or kw in ct or ct in kw`). 例: seg_keyword="防水材料" 包含 "防水" (clip_tag) → 算中
- 新脚本 `scripts/batch_sync_slice_to_library.py`: 一键把 6 个 completed 切片项目所有 clip 批量入资源库
  - 调 `POST /library/from-clip` (已有 endpoint), 跳过 source_clip_id 已存在的
  - 实测 +49 真素材 (含 5 个 fake upload 跳过, 25 日常直播1 已加过)
- 2 个新 test (`test_substring_命中_v2_2_36` / `test_substring_反向_v2_2_36`)

## v2.2.35 — wizard Step 1 实时分段预览 (2026-07-26)
**feat(mix)**: Step 1 wizard textarea 实时调 LLM 抽视觉关键词 + 分段预览.

- 新 endpoint `POST /api/v1/mix/parse-script` (单独暴露 `parse_script`)
  - 接 (script_text, target_duration_seconds=60) → 返 `{segments: [{position, text, keywords}], count}`
- 前端 Step 1 改: textarea 改 → debounce 1.5s → 调 `/parse-script` → 显示 N 段 + 每段视觉关键词
  - "关键词" 标签用暖色/海洋配色, 折叠/展开
- 新 CSS `.segment-preview-box` / `.segment-keyword-tag` 等 12 条样式
- 6 个新 test (`tests/test_parse_script_endpoint.py`)

## v2.2.34 — Task model 漏 4 列 (2026-07-26)
**fix(backend)**: User 报 POST /process 500 错 (user project cba4fbcb).

- **Root cause** (4afb777 refactor drift 同款):
  - `Task` model 漏 `estimated_total_at_start_seconds` / `actual_total_seconds` / `subtitle_status` / `subtitle_error` 4 列
  - db schema 有 (raw SQL migration 加过), ORM 没, 漂 2+ 个月
  - 触发 `TypeError: 'estimated_total_at_start_seconds' is an invalid keyword argument for Task`
- **修法**: 加 4 列回 `Task` model
- **通用防回归**: 新 `tests/test_model_db_drift.py` — model 列 vs db 实际列一致性 check. `MODEL_TABLES` 注册 (Style + Task), 任何 model 漏 db 已有的列 → test fail

## v2.2.33 — 视觉匹配 (2026-07-26)
**feat(mix)**: User 重新定义混剪 — "按播音稿语义分段, 每段找画面匹配素材".

- **修法** (`match_clips_for_segments`):
  - score = `0.7 * tag_overlap + 0.3 * embed_score`
  - tag_overlap = `|seg.keywords ∩ clip.tags| / |seg.keywords|` (0-1)
  - embed 降到 0.3 辅助 (text-to-text 相似, 当作辅助)
- `parse_script` prompt 强调"视觉关键词" (屋顶/瓦片/雨), 不是"主题词" (防水/品质)
- `build_clip_library_from_slice_db`: ResourceClip.tags 字段透传 (之前只 title+subtitle)
- 7 个新 test (`tests/test_mix_visual_match.py`)

## v2.2.32 — Style model 漏 2 列 (2026-07-26)
**fix(backend)**: User 报 PUT /config 500 错 (user project 598ab382).

- **Root cause** (4afb777 refactor drift):
  - `Style` model 漏 `pre_padding_seconds` / `post_padding_seconds` 2 列
  - 触发 `AttributeError: 'Style' object has no attribute 'pre_padding_seconds'`
- **修法**: 加 2 列回 `Style` model (Float default 10.0/5.0)
- 4 个新 test (`tests/test_style_model_padding.py`)

## v2.2.31 — UploadProgressBar 加 formatTime import (2026-07-26)
**fix(frontend)**: User 报 console 红屏 `formatTime is not defined`.

- 跟 v2.2.28 (formatBytes) / v2.2.29 (formatSpeed) 同款漏 import
- 修: `import { formatBytes, formatSpeed, formatTime } from '../ChunkedUploader'`

## v2.2.30 — ErrorBoundary 兜底 (2026-07-26)
**feat(frontend)**: React 组件崩了不让 Topbar 全挂.

- 新 `frontend/src/ErrorBoundary.jsx`: React class component, 任何子组件崩了显示"刷新重试" + dev 模式显示 stack trace
- `App.jsx` 在 `WatchFolders` / `TrashView` / `reel-grid` 三个易崩区包 `<ErrorBoundary>`
- CSS 用项目配色 (暖色夕阳/海洋蓝绿), 不用裸 Material 风格
- 5 个新 test (`tests/ErrorBoundary.test.jsx`)

---

## 测试覆盖
| 类别 | 数量 | 状态 |
|---|---|---|
| pytest | **237** | 5/5 跑稳 |
| vitest | **18** | 6/6 跑稳 (ErrorBoundary + ProjectCard + ThemeToggle 等) |
| pre-commit 3 关 | ruff + pytest subset + vitest | 全过 |
| 进程 | 13 healthy (release 3 / beta 3 / mix 1 + release 1 / beta 1 / mix 1 / uvicorn :8000 + :8030) | ✓ |

## 已知 bug / backlog (v2.2.44+)
- 真实视觉模型打标 (macOS Vision / moondream 本地 / OpenAI Vision API key) — 现有 tags 来自 LLM 用字幕反推, 不准
- beta 混剪完整修 (v2.2.37 改 dispatch, 但 build_clip_library 仍走 release 切片 db, 半步)
- CHANGELOG 跟 git tag 同步自动化 (每次 release 跟 push tag)
