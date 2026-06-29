# Issue Triage 2026-06-29

对原清单 9 条逐一校准,本工作区只动该动的(修 P0#1 + 测试),其余写明依据。
所有结论基于当前 HEAD (`refactor/video-service-cleanup` 分支, 与 `origin/main` @ `896b733` 同步),不预测未来。

## 真实修复

### [P0#1] step 3 (`create_timeline`) 公式算错 — 已修
- 位置: `backend/services/llm_service.py:357` (`_create_timeline_with_llm` 函数体内联)
- 根因: stride 公式多乘了 `len(parsed_segments)`,对 1.5GB SRT (~5000 段, 150k 字符) 算出 step=7651, 几乎全跳过
- 修法: `step = len(srt_compact) // MAX_CHARS + 1` (1 行)
- 验证: `tests/test_compact_srt_stride.py`,纯函数对比新旧公式,无需 ffmpeg/LLM/DB
- 配套: ponytail 注释 cross-ref P2#8(分块是更彻底的解,这次先纠正公式)

## 误报 (代码里不存在该问题)

### [P0#2] watchdog 30 分钟 mark failed — **真 bug, ponytail 之前判误报判错了**

**2026-06-29 14:51 用户反馈**:
- 阿甘正传 (3.6h 1GB) 跟 26429Demo (3.6h 1GB),14:15 启动 → 14:45 (30 分钟后) 被 _cleanup_stuck_tasks 标 task.status=failed + project.status=failed
- 实际 worker 还在跑 step 7 (切 clip 到 12-15/35 / 15-19)
- 跟 1GB 20260629测试2 同样的模式

**真实位置**: `_cleanup_stuck_tasks` 在 `backend/api/projects.py` 的 `list_projects` 入口调用,代码来自 beta 分支 v2.1.18 commit `a146818` (卡死 task 自动清理),在 main 跟 refactor WIP 都有。ponytail 之前在 main @ 896b733 上搜"stuck|mark_failed|1800"没匹到,是因为 rg pattern 没覆盖到 "_cleanup_stuck_tasks" 全名。

**根因 (a146818 commit message + 14:51 现象反推)**:
1. 判定维度错: `created_at < utcnow - 30min` 当作"卡死"—— 但 created_at 是 task 创建时间,大视频 1GB 跑 50-60 分钟正常
2. 阈值没自适应: 1GB 视频跟 100MB 视频处理时间差 10 倍,统一 30 分钟不合理
3. 触发时机紧耦合: list_projects 入口每次调用都跑,跟用户操作耦合,容易"侥幸结果对"(worker 跑完覆盖)

**已有修复**: refactor/video-service-cleanup WIP 已经删了 _cleanup_stuck_tasks(包括 list_projects 入口的调用)。v2.1.41 另有 "卡死 task recovery" 新设计。

**当前 macOS 部署的 v2.1.52 (从 main 拉的) 仍然有 bug**:
- main 没合 refactor WIP,所以 macOS 跑的代码还有 _cleanup_stuck_tasks
- 临时方案: 把 30 分钟阈值拉高(60 或 90),不解决根因,只延长窗口
- 真正方案: 跟 WIP 同步合 refactor,等 v2.1.41 recovery 逻辑完整

**处理**: macOS 端 `git pull` 拿 WIP + 等合 main; ponytail 不在 macOS 部署上改代码(没 token 之外的访问渠道)

### [P0#3] v2.1.52 没 tag — 误报
- `git tag -l` 末尾有 `v2.1.52`
- 处理: 不动

### [P1#4] `check_workers.sh` 漏 ForkPoolWorker — 误报
- 脚本注释明写 "期望 >= 6 (1 main + 5 forkpool)"
- `beta_count=$(ps aux | grep celery -A ... | wc -l)` 数的是所有 worker 进程行,不是父进程
- 处理: 不动

### [P1#5] venv 重建漏 moviepy — 误报
- `requirements.txt` 注释明写 "使用 subprocess 调用 ffmpeg, 不需要 av 库"
- `rg "moviepy" backend/**/*.py` 0 命中
- 处理: 不动

### [P1#6] worker 用错 Python 解释器 — 误报
- 4bf508d 已修 (`fix(scripts): start-beta.sh / start-release.sh 用 .venv/bin/python`)
- 处理: 不动

## 不该我做的

### [P1#7] release 分支 deploy 没同步 v2.1.52
- 事实: `origin/release/v1.0` 跟 `origin/main` 差 64 个 commit
- 性质: 跨分支部署同步是 owner 决策 (Dockerfile / docker-compose / 现有部署清单)
- 我没 push 上 origin 的权限, 也不该擅自 cherry-pick 64 个 commit
- 处理: 留给 owner, 提一个 follow-up

### [P2#9] test TypeError 根因未确诊
- 候选: `.pyc` 缓存 stale / Python 3.9 sys.path 不一致
- 我没在跑 beta 的 test 环境, 无复现命令
- 处理: 留给有现场的人

## P2#8 备注

P2#8 (step 3 应该分块而非采样) 跟 P0#1 是同一个函数的两种修法。
本次只动公式 (最小 diff, 风险可控), ponytail 注释里标了 "已知上限 + P2#8 升级路径"。
分块是更彻底的解, 留给后续 PR。
