# Video Clipper 快速启动指南

## 首次启动

### 1. 安装依赖

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper

# 检查 Redis
redis-cli ping  # 应该返回 PONG

# 如果没有 Redis，安装：
brew install redis  # macOS
# 然后启动：brew services start redis
```

### 2. 启动后端

```bash
# 方式 A: 使用启动脚本（推荐）
bash scripts/start.sh

# 方式 B: 手动启动
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 终端 1: 启动 Celery
celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q celery,processing

# 终端 2: 启动 FastAPI
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 访问应用

- 前端：http://localhost:3000
- API 文档：http://localhost:8000/docs

## 使用流程

1. 打开 http://localhost:3000
2. 点击"选择文件"上传视频
3. 输入项目名称
4. 点击"开始处理"
5. 等待处理完成（可在日志中查看进度）
6. 查看生成的切片和合集

## 常见问题

### Q: Redis 连接失败
```bash
# 检查 Redis 是否运行
redis-cli ping

# 如果没有运行，启动它
redis-server
# 或 macOS
brew services start redis
```

### Q: Celery Worker 未启动
```bash
# 检查进程
ps aux | grep celery

# 手动启动
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
source venv/bin/activate
celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q celery,processing
```

### Q: 字幕生成失败
- 检查 `.env` 文件中 `DASHSCOPE_API_KEY` 是否正确
- 查看后端日志中的详细错误信息

## 项目目录

```
video-clipper/
├── data/projects/        # 项目文件存储目录
├── backend/              # 后端代码
├── frontend/             # 前端代码
└── scripts/              # 启动脚本
```

## 停止服务

按 `Ctrl+C` 停止所有服务，或：

```bash
# 停止 Celery
pkill -f "celery.*video_clipper"

# 停止 FastAPI
pkill -f "uvicorn.*backend.main"
```
