# Video Clipper 部署文档

## 📋 版本隔离架构

| 组件 | 正式版 v1.0 | 测试版 v1.1-beta |
|------|------------|-----------------|
| **Git 分支** | `release/v1.0` | `main` |
| **前端端口** | 3000 | 3030 |
| **后端端口** | 8000 | 8030 |
| **数据库** | `data/video_clipper.db` | `data/video_clipper_beta.db` |
| **Redis DB** | `redis://localhost:6379/0` | `redis://localhost:6379/1` |
| **Celery 队列** | `processing` | `processing_beta` |

---

## 🚀 快速启动

### 启动正式版

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
./start-release.sh
```

**访问地址：** http://localhost:3000

### 启动测试版

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
./start-beta.sh
```

**访问地址：** http://localhost:3030

---

## 🔧 手动启动（不推荐使用）

### 正式版组件

```bash
# 1. 启动后端 (8000)
DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db" \
CELERY_BROKER_URL="redis://localhost:6379/0" \
CELERY_RESULT_BACKEND="redis://localhost:6379/0" \
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 2. 启动 Worker
CELERY_BROKER_URL="redis://localhost:6379/0" \
CELERY_RESULT_BACKEND="redis://localhost:6379/0" \
CELERY_QUEUE_NAME="processing" \
python3 -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing

# 3. 启动前端 (3000)
cd frontend
VITE_PORT="3000" VITE_API_PORT="8000" npm run dev -- --port 3000
```

### 测试版组件

```bash
# 1. 启动后端 (8030)
DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db" \
CELERY_BROKER_URL="redis://localhost:6379/1" \
CELERY_RESULT_BACKEND="redis://localhost:6379/1" \
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8030

# 2. 启动 Worker
CELERY_BROKER_URL="redis://localhost:6379/1" \
CELERY_RESULT_BACKEND="redis://localhost:6379/1" \
CELERY_QUEUE_NAME="processing_beta" \
python3 -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing_beta

# 3. 启动前端 (3030)
cd frontend
VITE_PORT="3030" VITE_API_PORT="8030" npm run dev -- --port 3030
```

---

## ✅ 验证隔离

### 1. 检查后端 API

```bash
# 正式版
curl -s http://localhost:8000/api/v1/projects/ | python3 -c "import sys,json; d=json.load(sys.stdin); print('正式版项目数:', len(d['projects']))"

# 测试版
curl -s http://localhost:8030/api/v1/projects/ | python3 -c "import sys,json; d=json.load(sys.stdin); print('测试版项目数:', len(d['projects']))"
```

### 2. 检查数据库

```bash
# 正式版数据库
sqlite3 data/video_clipper.db "SELECT COUNT(*) FROM projects;"

# 测试版数据库
sqlite3 data/video_clipper_beta.db "SELECT COUNT(*) FROM projects;"
```

### 3. 检查进程

```bash
# 查看 uvicorn 进程
ps aux | grep uvicorn | grep -v grep

# 查看 celery 进程
ps aux | grep celery | grep -v grep

# 查看 vite 进程
ps aux | grep vite | grep -v grep
```

---

## 🛑 停止服务

```bash
# 停止所有服务
pkill -f "uvicorn.*8000"
pkill -f "uvicorn.*8030"
pkill -f "celery.*processing"
pkill -f "celery.*processing_beta"
pkill -f "vite.*3000"
pkill -f "vite.*3030"
```

---

## 📁 关键配置文件

### 后端配置 (`backend/core/config.py`)

```python
# 支持环境变量覆盖
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/video_clipper.db")
CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_QUEUE_NAME: str = os.getenv("CELERY_QUEUE_NAME", "processing")
```

### Celery 配置 (`backend/core/celery_app.py`)

```python
# 从环境变量获取配置
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
CELERY_QUEUE_NAME = os.getenv("CELERY_QUEUE_NAME", "processing")
```

### 前端配置 (`frontend/vite.config.js`)

```javascript
// 从环境变量读取配置
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

## ⚠️ 常见问题

### Q: 两个版本数据混在一起？

**原因：** 启动时没有设置正确的环境变量

**解决：**
1. 停止所有服务
2. 使用 `./start-release.sh` 和 `./start-beta.sh` 启动
3. 验证数据库文件：
   - 正式版：`data/video_clipper.db` (有数据)
   - 测试版：`data/video_clipper_beta.db` (空或测试数据)

### Q: 前端访问后端返回空数据？

**原因：** Vite 缓存了旧的代理配置

**解决：**
```bash
# 清除 Vite 缓存
rm -rf frontend/node_modules/.vite

# 重启前端
pkill -f "vite.*3000"
pkill -f "vite.*3030"
./start-release.sh  # 或 ./start-beta.sh
```

### Q: 如何完全重置测试版？

```bash
# 停止测试版服务
pkill -f "uvicorn.*8030"
pkill -f "celery.*processing_beta"
pkill -f "vite.*3030"

# 删除测试版数据库
rm data/video_clipper_beta.db

# 重启测试版
./start-beta.sh
```

---

## 📊 服务状态检查清单

启动后执行以下检查：

```bash
# 1. 检查后端健康
curl -s http://localhost:8000/health  # 应返回 {"status":"healthy"}
curl -s http://localhost:8030/health  # 应返回 {"status":"healthy"}

# 2. 检查数据库隔离
echo "正式版数据库:" && sqlite3 data/video_clipper.db "SELECT COUNT(*) FROM projects;"
echo "测试版数据库:" && sqlite3 data/video_clipper_beta.db "SELECT COUNT(*) FROM projects;"

# 3. 检查前端代理
echo "正式版前端:" && curl -s http://localhost:3000/api/v1/projects/ | python3 -c "import sys,json; print(len(json.load(sys.stdin)['projects']), '个项目')"
echo "测试版前端:" && curl -s http://localhost:3030/api/v1/projects/ | python3 -c "import sys,json; print(len(json.load(sys.stdin)['projects']), '个项目')"
```

---

## 📝 版本发布流程

### 发布新版本到正式版

```bash
# 1. 在 main 分支完成开发和测试
git checkout main
# ... 开发、测试 ...

# 2. 合并到 release 分支
git checkout release/v1.0
git merge main
git tag -a v1.1 -m "Release v1.1"

# 3. 推送
git push origin release/v1.0 --tags

# 4. 重启正式版
pkill -f "uvicorn.*8000"
pkill -f "vite.*3000"
./start-release.sh
```

---

**最后更新：** 2026-04-08  
**维护者：** 剪辑小助理 ✂️
