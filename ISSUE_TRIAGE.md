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

### [P0#2] watchdog 30 分钟 mark failed — 误报
- 描述指向 `backend/api/projects.py:261-280` `_cleanup_stuck_tasks`
- 实际: `rg "stuck|mark_failed|1800|30 * 60"` 全文件 0 命中;261-280 行是 `_build_timing_info` 跟 ETA 估算,跟 task 失败判定无关
- worker 跑超时的处置是 launchd + celery 自身 timeout, 不在 backend 项目范围内
- 处理: 不动

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
