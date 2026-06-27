# 部署说明（局域网模式）

## 当前状态（2026-06-27）

外网服务（cloudflared + nginx）已关闭。**只支持本机 + 局域网访问**。

```
🌐 局域网 URL:    http://172.16.120.82:3030/
🖥️  本机 URL:     http://localhost:3030/
```

⚠️ **IP 是临时的**——Mac 切换 WiFi 会变。运行 `ifconfig en0` 看当前 IP。

## 架构

```
[运营同事浏览器（局域网）]
       ↓ HTTP
[vite dev :3030]   (host=0.0.0.0，前端 + /api proxy)
       ↓
[uvicorn :8030]    (host=0.0.0.0，backend)
       ↓
[celery worker]    (Whisper 转录 + 视频处理)
```

**没 basic auth**——局域网内信任，团队共用 1 个用户。

## 当前服务

| 进程 | 端口 | 进程 ID |
|---|---|---|
| vite | 3030 | (动态) |
| backend (uvicorn) | 8030 | (动态) |
| celery worker | - | (动态) |

## 重启后恢复

```bash
# 1. Redis
redis-server --daemonize yes

# 2. Backend (8030)
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
nohup env DATABASE_URL='sqlite+aiosqlite:///data/video_clipper_beta.db' \
  CELERY_BROKER_URL='redis://localhost:6379/1' \
  CELERY_RESULT_BACKEND='redis://localhost:6379/1' \
  CELERY_QUEUE_NAME=processing_beta \
  /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python \
  -m uvicorn backend.main:app --host 0.0.0.0 --port 8030 \
  > logs/backend_beta.log 2>&1 &

# 3. Vite (3030)
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
nohup node ./frontend/node_modules/.bin/vite --config frontend/vite.config.beta.js --port 3030 \
  > logs/frontend_beta.log 2>&1 &

# 4. Celery worker
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper
nohup env DATABASE_URL='sqlite+aiosqlite:///data/video_clipper_beta.db' \
  CELERY_QUEUE_NAME=processing_beta \
  CELERY_BROKER_URL='redis://localhost:6379/1' \
  CELERY_RESULT_BACKEND='redis://localhost:6379/1' \
  HF_ENDPOINT='https://hf-mirror.com' \
  HF_HUB_DOWNLOAD_TIMEOUT=60 \
  /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python \
  -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=5 -Q processing_beta \
  > /tmp/worker_beta.log 2>&1 &
```

## 限制

| 问题 | 说明 |
|---|---|
| 只局域网能用 | 同事得在同一个 WiFi 下 |
| IP 会变 | 切 WiFi 后运营需要新地址 |
| 单机处理 | 多人同时传排队 |
| 上传大文件慢 | 走家里上行，受限于带宽 |

## 升级路径（如以后要外网）

1. **重开 cloudflared**：下回外网时再 `nohup /tmp/cloudflared tunnel --url http://localhost:3030`
2. **重开 nginx basic auth**：保护局域网外暴露时的访问
3. **VPS 部署**：彻底解决单机瓶颈（几十块/月）

