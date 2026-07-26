# scripts/ — 维护 / 调试 / 数据回填工具

video-clipper 维护脚本说明. 跑前先看 `--help`, 看清默认 db / host.

## 工具列表

| 脚本 | 用途 | 用法 |
|---|---|---|
| `batch_sync_slice_to_library.py` | 一键把切片项目所有 clip 批量入资源库 | `python scripts/batch_sync_slice_to_library.py [--dry-run] [--host :8030]` |
| `backfill_resource_thumbnails.py` | 给已有没 thumbnail 的 resource 补 ffmpeg 抽 1 帧 | `python scripts/backfill_resource_thumbnails.py [--db path] [--dry-run]` |
| `reset_and_redispatch_mix.py` | 重置老 mix project (清 source_clips + output mp4) + 直接 dispatch_mix_task 重派发 | `python scripts/reset_and_redispatch_mix.py <project_id>` |
| `start.sh` / `start-frontend.sh` | 启 release/beta uvicorn + workers | `bash scripts/start.sh` |
| `check_workers.sh` | watchdog: 检查 worker 数量 + 7 天 uptime + broker 一致性 + auto restart | 配 launchd plist 每 5 min 跑 |

---

## 1. batch_sync_slice_to_library.py

**何时用**:
- 刚加 v2.2.5 资源库后, 想把已有 completed 切片项目所有 clip 快速入资源库
- 资源库被清空 / 删 db 后回填
- 跨 db 同步 (release → release, beta → beta 各 1 次)

**行为**:
- 查 `projects` 表 status='completed' AND deleted_at IS NULL 的所有项目
- 对每个项目循环 `POST /api/v1/library/from-clip` 端点
- 跳过 `source_clip_id` 已存在的 (去重, 不会重复 import)
- 礼貌限速 0.05s/request

**输出**:
```
📦 日常直播4 (e4d79f6a) — 5 clip
  ✓ + '顶楼防水这样选！...'
  ...
   +5 跳过 0
```

**注意**:
- 默认 host `http://127.0.0.1:8030` (beta), 跟 release 模式 run 改 `--host http://127.0.0.1:8000`
- 跑前确认 worker 在跑 (resource 入库需 celery worker 处理 from-clip 后台任务)
- dry-run 不写 db, 跑 1 次看哪些会被加

## 2. backfill_resource_thumbnails.py

**何时用**:
- 资源库显示无封面 / 缺缩略图
- v2.2.38 之前 from-clip 没兜底抽 thumbnail 时 import 的老资源

**行为**:
- 查 `resource_clips` 表 thumbnail_path 为空 / 文件不存在的所有 row
- ffmpeg 抽 1s 帧 (跟 `backend/api/library.py:_generate_thumbnail` 同款)
- 写回 `thumbnail_path` 字段

**输出**:
```
=== 完成: ✓81 ✗0 跳0 ===
```

**注意**:
- 实测: beta 81/81 ✓, release 75/79 (4 个 mp4 物理文件不存在 fail, 跟 thumbnail 无关)
- 跑 1 次即可, 没有副作用 (idempotent, 已有的 skip)

## 3. reset_and_redispatch_mix.py

**何时用**:
- v2.2.42 round-robin 修之前跑的 mix project 重复 (7 段 fallback 同 1 clip)
- 任何老 mix project 想重跑 (worker 不会清老 source_clips/output, 直接 dispatch 会 duplicate)
- 修 match 公式后批量重派发老 project 验证新行为

**行为**:
1. 找老 `source_clip_id` (3 unique from bc65f840)
2. DELETE `mix_source_clips` + `mix_tasks` WHERE `mix_project_id=?`
3. UPDATE `project.status='pending'` + 清 `output_video_path/duration/thumbnail`
4. DELETE 老 mp4 + thumbnail + `_extract_parts/`
5. `dispatch_mix_task` 直接调 (不创建新 project, 保留老 id + 引用)

**输出**:
```
=== 重置 bc65f840-... ===
candidate_clip_ids: 3 个
DELETE 8 老 source_clips + 1 老 task
project 重置为 pending
=== 重新派发 (直接 dispatch_mix_task) ===
  dispatched: task_id=...
```

**注意**:
- 默认用 release mode (db 0/processing_mix) dispatch, 跟 uvicorn :8000 一致
- 候选 clip 0 个时自动从 `release resource_clips` 找 8 个 from-project (兜底, 不让 dispatch 0 candidate raise)
- 跑前看 logs/celery_mix1.log 确认 worker 跑新代码 (v2.2.42 round-robin)

## 4. check_workers.sh (watchdog)

**何时启**:
- 配 launchd plist, 每 5 min 跑
- macOS dev mode 推荐: `~/Library/LaunchAgents/com.video-clipper.worker-watchdog.plist`

**行为**:
- 检查 release/beta worker 数量 < 期望 → 自动 restart
- 检查 worker uptime > 7 天 → 自动 restart (防 celery clock drift 累积)
- 检查 uvicorn 8000/8030 端口无人监听 → 通知 (osascript 弹窗)
- v2.2.23 broker 一致性 check (worker broker db 跟 uvicorn 一致)
- v2.2.37 `start_mix_worker` 启 **2 个** mix worker (release + beta 各 1)

**配置**:
- `WORKSPACE=/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper`
- `MAX_UPTIME_DAYS=7`
- `LOG_FILE=/tmp/video-clipper-worker-watchdog.log`

## 通用注意

- **跑前**确认 workspace 路径正确 (默认跟 mavis 启动目录一致, 改 hardcode)
- **subprocess.run** 用 `capture_output=True`, stdout/stderr 不污染调用方
- **db 修改**走 sqlite3 + transaction, 失败回滚
- **dispatch** 走 env 子进程 (跟 worker 一样的 CELERY_BROKER_URL + DATABASE_URL), 跨进程不要污染父进程 env

## 添加新脚本 checklist

- [ ] `chmod +x` 跑 1 次
- [ ] 顶部 docstring 写"何时用 + 行为 + 注意事项"
- [ ] `--dry-run` 支持 (任何会改 db/fs 的操作)
- [ ] 跑后输出"完成 N 个 / 失败 N 个 / 跳过 N 个"
- [ ] 失败时退出码 != 0 (跟 shell pipeline 配合)
- [ ] 写进 git + bump VERSION + push tag
