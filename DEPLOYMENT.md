# 外网部署说明

## 当前状态（2026-06-27）

```
🌐 URL:     https://smile-between-cambridge-kits.trycloudflare.com
👤 账号:    team
🔑 密码:    qXKj12J6tY7PmaSy
```

⚠️ cloudflared 临时 URL，**每次重启会变**。如果想固定 URL，需要绑定自己的域名。

## 架构

```
[运营同事浏览器]
       ↓ HTTPS
[cloudflared tunnel]   (pid 72018, /tmp/cloudflared)
       ↓
[nginx :8080]          (basic auth + 5GB 上传限制)
       ↓
[vite dev :3030]       (frontend + /api proxy)
       ↓
[uvicorn :8030]        (backend)
       ↓
[celery worker]        (Whisper 转录 + 视频处理)
```

## 重启后恢复

如果 Mac 重启或服务挂了，按顺序启动：

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
  -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing_beta \
  > /tmp/worker_beta.log 2>&1 &

# 5. Nginx (8080)
nginx -c /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/nginx-external.conf

# 6. Cloudflared（新 URL 会变）
nohup /tmp/cloudflared tunnel --no-autoupdate --url http://localhost:8080 > /tmp/cf.log 2>&1 &
# 等 5 秒看 URL
sleep 5 && grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/cf.log | head -1
```

## 修改密码

```bash
# 改 team 的密码
htpasswd -b /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.htpasswd team 新密码

# 加新用户
htpasswd -b /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.htpasswd 新用户名 新密码

# 重启 nginx 让密码生效
nginx -s reload -c /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/nginx-external.conf
```

## 当前限制（生产前必须解决）

| 问题 | 影响 | 临时方案 |
|---|---|---|
| 所有人共享一个账号 | 看得到全部项目，能删 | 团队 3-10 人用 + 沟通 + 信任 |
| 上传走家里上行 | 1GB 视频 5-30 分钟 | 让同事传小一点的视频 |
| cloudflared 临时 URL | 重启就变 | 把新 URL 同步给团队 |
| 单机烧录 | 1-2 个并发 | 多人排队，别同一时间传 |

## 升级路径（按成本排序）

1. **绑固定域名**（免费 + 简单）：cloudflared 建 named tunnel，URL 固定
2. **加 nginx 限流**（5 分钟）：防止一个人把带宽跑满
3. **加登录系统**（几小时）：JWT + 多账号 + 权限
4. **VPS 部署**（几十块/月）：彻底解决单机瓶颈
5. **容器化**（专业级）：Docker + k8s
