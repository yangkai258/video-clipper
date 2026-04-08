# Video Clipper 混合部署方案

**最后更新：** 2026-04-08  
**适用场景：** 国内网络环境，Docker Hub 访问受限

---

## 🎯 推荐方案：混合部署

### 架构

```
宿主机（macOS）
├─ 正式版
│   ├─ 前端：npm run dev (3000)
│   ├─ 后端：uvicorn (8000)
│   ├─ Worker: celery (processing)
│   └─ Redis: Docker 容器 (6379)
└─ 测试版
    ├─ 前端：npm run dev (3030)
    ├─ 后端：uvicorn (8030)
    ├─ Worker: celery (processing_beta)
    └─ Redis: Docker 容器 (6380)
```

### 优势

1. **Redis 隔离** - 使用 Docker 容器，避免安装 Redis
2. **前端/后端本地运行** - 不依赖 Docker Hub
3. **完全隔离** - 两个版本独立运行
4. **易于调试** - 代码直接在宿主机

---

## 🚀 快速开始

### 1. 启动 Redis 容器

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper

# 启动正式版 Redis
docker run -d --name vc-redis-release \
  -p 6379:6379 \
  -v redis_release_data:/data \
  redis:7-alpine

# 启动测试版 Redis
docker run -d --name vc-redis-beta \
  -p 6380:6379 \
  -v redis_beta_data:/data \
  redis:7-alpine
```

### 2. 启动正式版

```bash
# 后端
DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db" \
CELERY_BROKER_URL="redis://localhost:6379/0" \
CELERY_RESULT_BACKEND="redis://localhost:6379/0" \
CELERY_QUEUE_NAME="processing" \
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# Worker
DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db" \
CELERY_BROKER_URL="redis://localhost:6379/0" \
CELERY_RESULT_BACKEND="redis://localhost:6379/0" \
CELERY_QUEUE_NAME="processing" \
celery -A backend.core.celery_app worker --loglevel=info --concurrency=4 -Q processing &

# 前端
cd frontend && npm run dev -- --port 3000
```

### 3. 启动测试版

```bash
# 后端
DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db" \
CELERY_BROKER_URL="redis://localhost:6380/0" \
CELERY_RESULT_BACKEND="redis://localhost:6380/0" \
CELERY_QUEUE_NAME="processing_beta" \
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8030 &

# Worker
DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db" \
CELERY_BROKER_URL="redis://localhost:6380/0" \
CELERY_RESULT_BACKEND="redis://localhost:6380/0" \
CELERY_QUEUE_NAME="processing_beta" \
celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing_beta &

# 前端
cd frontend && npm run dev -- --port 3030
```

---

## 📋 管理脚本

### start-redis.sh

```bash
#!/bin/bash
# 启动 Redis 容器

cd "$(dirname "$0")"

# 检查是否已运行
if docker ps | grep -q vc-redis-release; then
  echo "✅ 正式版 Redis 已运行"
else
  echo "🚀 启动正式版 Redis..."
  docker run -d --name vc-redis-release \
    -p 6379:6379 \
    -v $(pwd)/redis_release_data:/data \
    redis:7-alpine
fi

if docker ps | grep -q vc-redis-beta; then
  echo "✅ 测试版 Redis 已运行"
else
  echo "🚀 启动测试版 Redis..."
  docker run -d --name vc-redis-beta \
    -p 6380:6379 \
    -v $(pwd)/redis_beta_data:/data \
    redis:7-alpine
fi

echo ""
echo "✅ Redis 已启动"
echo "  正式版：localhost:6379"
echo "  测试版：localhost:6380"
```

### start-all-local.sh

```bash
#!/bin/bash
# 本地启动所有服务（不使用 Docker）

cd "$(dirname "$0")"

echo "🚀 启动 Video Clipper（本地模式）"
echo ""

# 启动 Redis
./start-redis.sh

sleep 2

# 启动正式版
echo ""
echo "=== 正式版 ==="
./start-release.sh &

sleep 5

# 启动测试版
echo ""
echo "=== 测试版 ==="
./start-beta.sh &

echo ""
echo "✅ 所有服务已启动"
echo ""
echo "访问地址："
echo "  正式版：http://localhost:3000"
echo "  测试版：http://localhost:3030"
```

---

## 🔧 故障排查

### Redis 连接失败

```bash
# 检查 Redis 容器
docker ps | grep vc-redis

# 查看 Redis 日志
docker logs vc-redis-release

# 测试连接
redis-cli -p 6379 ping
redis-cli -p 6380 ping
```

### 清理 Redis 容器

```bash
# 停止并删除
docker stop vc-redis-release vc-redis-beta
docker rm vc-redis-release vc-redis-beta

# 重新启动
./start-redis.sh
```

---

## 📊 对比方案

| 项目 | 纯 Docker | 混合部署 | 纯本地 |
|------|----------|----------|--------|
| Redis 隔离 | ✅ | ✅ | ❌ |
| 前端隔离 | ✅ | ❌ | ❌ |
| 后端隔离 | ✅ | ✅ | ❌ |
| 数据库隔离 | ✅ | ✅ | ✅ |
| 网络依赖 | 高 | 低 | 无 |
| 启动速度 | 慢 | 快 | 快 |
| 调试便利 | 中 | 高 | 高 |
| 推荐度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

---

**推荐：使用混合部署方案！** 🎯
