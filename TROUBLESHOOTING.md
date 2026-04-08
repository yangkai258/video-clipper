# Video Clipper 问题排查手册

**最后更新：** 2026-04-08  
**维护者：** 剪辑小助理 ✂️

---

## 📋 目录

1. [版本隔离问题](#1-版本隔离问题)
2. [前端代理配置问题](#2-前端代理配置问题)
3. [Celery 任务队列问题](#3-celery-任务队列问题)
4. [视频播放卡顿问题](#4-视频播放卡顿问题)
5. [Worker 进程未启动](#5-worker-进程未启动)
6. [快速诊断命令](#6-快速诊断命令)

---

## 1. 版本隔离问题

### 症状

- 在 3030（测试版）删除项目，3000（正式版）的项目也消失
- 两个版本显示相同的项目列表
- 上传视频到测试版，正式版也能看到

### 根本原因

启动时没有正确设置环境变量，导致：
- 两个版本使用同一个数据库
- 两个版本使用同一个 Redis DB
- 两个版本使用同一个 Celery 队列

### 解决方案

**✅ 正确做法：使用启动脚本**

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper

# 启动正式版
./start-release.sh

# 启动测试版
./start-beta.sh
```

**❌ 错误做法：手动启动**

```bash
# 不要这样做！
git checkout main && cd frontend && npm run dev -- --port 3030
```

### 隔离架构

```
正式版 v1.0 (release/v1.0 分支)
├─ 前端：3000 → 代理到 8000
├─ 后端：8000
├─ 数据库：data/video_clipper.db
└─ Worker: Redis DB 0, queue: processing

测试版 v1.1-beta (main 分支)
├─ 前端：3030 → 代理到 8030
├─ 后端：8030
├─ 数据库：data/video_clipper_beta.db
└─ Worker: Redis DB 1, queue: processing_beta
```

### 验证命令

```bash
# 检查数据库隔离
sqlite3 data/video_clipper.db "SELECT COUNT(*) FROM projects;"
sqlite3 data/video_clipper_beta.db "SELECT COUNT(*) FROM projects;"

# 检查后端 API
curl -s http://localhost:8000/api/v1/projects/ | python3 -c "import sys,json; print('8000:', len(json.load(sys.stdin)['projects']))"
curl -s http://localhost:8030/api/v1/projects/ | python3 -c "import sys,json; print('8030:', len(json.load(sys.stdin)['projects']))"

# 检查前端代理
curl -s http://localhost:3000/api/v1/projects/ | python3 -c "import sys,json; print('3000:', len(json.load(sys.stdin)['projects']))"
curl -s http://localhost:3030/api/v1/projects/ | python3 -c "import sys,json; print('3030:', len(json.load(sys.stdin)['projects']))"
```

---

## 2. 前端代理配置问题

### 症状

- 3000 和 3030 显示相同的内容
- 删除一个版本的项目，另一个版本也消失
- 前端返回空数据，但后端 API 正常

### 根本原因

1. **Vite 缓存共享**：两个前端进程共享 `frontend/node_modules/.vite` 缓存
2. **Git 分支切换**：手动切换分支启动导致配置混乱
3. **代理配置错误**：前端代理指向错误的后端端口

### 解决方案

**✅ 步骤 1：清理缓存**

```bash
pkill -f "vite.*3000"
pkill -f "vite.*3030"
rm -rf frontend/node_modules/.vite
```

**✅ 步骤 2：使用启动脚本**

```bash
./start-release.sh  # 自动处理分支和缓存
./start-beta.sh     # 自动处理分支和缓存
```

**✅ 步骤 3：验证代理配置**

```bash
# 检查 3000 前端代理（应指向 8000）
curl -s http://localhost:3000/api/v1/projects/

# 检查 3030 前端代理（应指向 8030）
curl -s http://localhost:3030/api/v1/projects/
```

### 配置文件

**正式版 (release/v1.0) vite.config.js：**

```javascript
export default defineConfig({
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

**测试版 (main) vite.config.js：**

```javascript
const PORT = parseInt(process.env.VITE_PORT || '3030', 10)
const API_PORT = parseInt(process.env.VITE_API_PORT || '8030', 10)

export default defineConfig({
  server: {
    port: PORT,
    proxy: {
      '/api': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
})
```

---

## 3. Celery 任务队列问题

### 症状

- 项目进度卡在 15%（生成字幕中）不动
- Worker 日志没有收到任务
- Redis 队列为空，但任务状态是 `running`

### 根本原因

**`backend/api/projects.py` 中的 `send_task` 硬编码了队列名：**

```python
# ❌ 错误写法
celery_task = temp_app.send_task(
    "backend.tasks.processing.process_video_pipeline",
    args=[...],
    queue="processing",  # 硬编码！
)
```

导致测试版任务发送到 `processing` 队列，但 Worker 监听的是 `processing_beta`。

### 解决方案

**✅ 修改为从环境变量读取：**

```python
# backend/api/projects.py
import os
from celery import Celery

broker_url = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
queue_name = os.getenv("CELERY_QUEUE_NAME", "processing")

temp_app = Celery("temp", broker=broker_url, backend=result_backend)

celery_task = temp_app.send_task(
    "backend.tasks.processing.process_video_pipeline",
    args=[project_id, str(video_path), srt_path, task.id],
    queue=queue_name,  # ✅ 使用环境变量
)
```

### 验证命令

```bash
# 检查队列长度
redis-cli -n 0 LLEN processing       # 正式版队列
redis-cli -n 1 LLEN processing_beta  # 测试版队列

# 检查 Worker 是否收到任务
# 查看 Worker 日志（start-*.sh 输出）
```

---

## 4. 视频播放卡顿问题

### 症状

- 视频声音正常播放，但画面卡顿
- 拖动进度条后卡顿更明显
- 浏览器播放不流畅

### 根本原因

**使用流复制 (`-c copy`) 导致：**

1. 关键帧间隔太长（依赖源视频，可能 5-10 秒一个关键帧）
2. 浏览器 seek 需要等待关键帧
3. 编码格式不兼容某些浏览器

### 解决方案

**✅ 使用 VideoToolbox 硬件加速重新编码：**

```python
# backend/services/video_service.py
subprocess.run([
    "ffmpeg", "-y",
    "-i", str(input_video),
    "-ss", str(start),
    "-t", str(duration),
    "-c:v", "h264_videotoolbox",
    "-keyint_min", "30",      # 最小关键帧间隔 30 帧
    "-g", "30",               # 最大关键帧间隔 30 帧（1 秒）
    "-profile:v", "high",     # H.264 High Profile
    "-level", "4.0",          # Level 4.0
    "-c:a", "aac",            # AAC 音频
    "-b:a", "128k",           # 128k 比特率
    "-movflags", "+faststart", # MOOV 在文件开头
    str(output_path)
], check=True, capture_output=True)
```

### 关键参数说明

| 参数 | 值 | 作用 |
|------|-----|------|
| `-g` | 30 | 每 30 帧（1 秒）一个关键帧，保证流畅 seek |
| `-profile:v` | high | H.264 High Profile，兼容所有浏览器 |
| `-movflags +faststart` | - | MOOV 在文件开头，支持边下边播 |
| `-c:v h264_videotoolbox` | - | macOS 硬件加速，速度 3-5 倍 |

### 重新处理

**已生成的视频需要重新处理才能应用新编码：**

1. 删除旧项目
2. 重新上传视频
3. 等待处理完成

---

## 5. Worker 进程未启动

### 症状

- 项目进度一直卡在 15%
- 后端 API 正常，但任务不执行
- Redis 队列有任务堆积

### 根本原因

**启动脚本语法错误：**

```bash
# start-beta.sh 第 39 行引号不匹配
./start-beta.sh: line 39: unexpected EOF while looking for matching `"'
```

导致 Worker 进程启动失败。

### 解决方案

**✅ 检查脚本语法：**

```bash
bash -n start-beta.sh  # 语法检查
bash -n start-release.sh
```

**✅ 重启服务：**

```bash
pkill -f "celery.*processing"
pkill -f "uvicorn.*8030"
./start-beta.sh
```

**✅ 验证 Worker 状态：**

```bash
ps aux | grep celery | grep -v grep
# 应看到 processing 和 processing_beta 两个队列的 Worker
```

---

## 6. 快速诊断命令

### 一键检查脚本

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
./check-status.sh
```

### 手动诊断

```bash
# 1. 检查进程
ps aux | grep -E "vite|uvicorn|celery" | grep -v grep

# 2. 检查数据库
sqlite3 data/video_clipper.db "SELECT COUNT(*) FROM projects;"
sqlite3 data/video_clipper_beta.db "SELECT COUNT(*) FROM projects;"

# 3. 检查后端 API
curl -s http://localhost:8000/health
curl -s http://localhost:8030/health

# 4. 检查 Celery 队列
redis-cli -n 0 LLEN processing
redis-cli -n 1 LLEN processing_beta

# 5. 检查前端代理
curl -s http://localhost:3000/api/v1/projects/ | python3 -c "import sys,json; print('3000:', len(json.load(sys.stdin)['projects']))"
curl -s http://localhost:3030/api/v1/projects/ | python3 -c "import sys,json; print('3030:', len(json.load(sys.stdin)['projects']))"
```

### 重置服务

```bash
# 停止所有服务
pkill -f "vite"
pkill -f "uvicorn"
pkill -f "celery"

# 清理 Vite 缓存
rm -rf frontend/node_modules/.vite

# 重启服务
./start-release.sh
./start-beta.sh
```

---

## 📚 相关文档

- `DEPLOYMENT.md` - 完整部署文档
- `DESIGN.md` - 前端设计规范
- `skills/video-clipper-isolation/SKILL.md` - 版本隔离问题排查技能

---

## 🎯 最佳实践

### ✅ 应该做的

1. **始终使用启动脚本**：`./start-release.sh` 和 `./start-beta.sh`
2. **定期检查服务状态**：`./check-status.sh`
3. **重新处理视频时删除旧项目**：确保使用新编码
4. **提交代码前测试两个版本**：确保隔离正常

### ❌ 不应该做的

1. **不要手动切换 Git 分支启动前端**：会破坏 Vite 缓存
2. **不要同时手动启动两个前端**：配置会互相覆盖
3. **不要直接修改数据库**：使用 API 操作
4. **不要忽略 Worker 日志**：问题通常能在日志中找到

---

**最后更新：** 2026-04-08  
**维护者：** 剪辑小助理 ✂️
