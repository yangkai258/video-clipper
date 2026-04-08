# Video Clipper Docker 完整部署指南

**最后更新：** 2026-04-08  
**版本：** v2.0（完整版）

---

## 📋 目录

1. [架构概览](#架构概览)
2. [快速开始](#快速开始)
3. [服务说明](#服务说明)
4. [数据管理](#数据管理)
5. [网络配置](#网络配置)
6. [监控与日志](#监控与日志)
7. [备份与恢复](#备份与恢复)
8. [故障排查](#故障排查)
9. [生产环境优化](#生产环境优化)

---

## 架构概览

### 完整架构图

```
┌─────────────────────────────────────────────────────┐
│                  Docker Network                      │
│                   vc-network                         │
│                                                      │
│  ┌──────────────┐    ┌──────────────┐               │
│  │ 正式版前端   │    │ 测试版前端   │               │
│  │   nginx:80   │    │  nginx:8080  │               │
│  └──────┬───────┘    └──────┬───────┘               │
│         │                   │                        │
│  ┌──────▼───────┐    ┌──────▼───────┐               │
│  │ 正式版后端   │    │ 测试版后端   │               │
│  │  Python:8000 │    │  Python:8030 │               │
│  └──────┬───────┘    └──────┬───────┘               │
│         │                   │                        │
│  ┌──────▼───────┐    ┌──────▼───────┐               │
│  │ 正式版 Worker│    │ 测试版 Worker│               │
│  │   Celery     │    │   Celery     │               │
│  └──────┬───────┘    └──────┬───────┘               │
│         │                   │                        │
│  ┌──────▼───────┐    ┌──────▼───────┐               │
│  │ 正式版 Redis │    │ 测试版 Redis │               │
│  │   6379       │    │   6379       │               │
│  └──────────────┘    └──────────────┘               │
│                                                      │
│  ┌──────────────────────────────────────┐           │
│  │        数据卷（持久化）               │           │
│  │  - release_data (正式版数据库)        │           │
│  │  - beta_data (测试版数据库)           │           │
│  │  - redis_release_data                 │           │
│  │  - redis_beta_data                    │           │
│  └──────────────────────────────────────┘           │
└─────────────────────────────────────────────────────┘

外部访问:
  - 正式版前端：http://localhost:80
  - 正式版后端：http://localhost:8000
  - 测试版前端：http://localhost:8080
  - 测试版后端：http://localhost:8030
  - Redis 可视化：http://localhost:8081
```

### 服务清单

| 服务 | 容器名 | 端口 | 用途 |
|------|--------|------|------|
| **正式版** |
| 前端 | vc-frontend-release | 80 | Nginx 静态服务 |
| 后端 | vc-backend-release | 8000 | FastAPI API |
| Worker | vc-worker-release | - | Celery 异步任务 |
| Redis | vc-redis-release | 6379 | 消息队列 |
| **测试版** |
| 前端 | vc-frontend-beta | 8080 | Nginx 静态服务 |
| 后端 | vc-backend-beta | 8030 | FastAPI API |
| Worker | vc-worker-beta | - | Celery 异步任务 |
| Redis | vc-redis-beta | 6380 | 消息队列 |
| **监控** |
| Redis Commander | vc-redis-commander | 8081 | Redis 可视化 |

---

## 快速开始

### 前置条件

```bash
# 安装 Docker Desktop (macOS)
# https://www.docker.com/products/docker-desktop/

# 验证安装
docker --version
docker-compose --version
```

### 一键启动

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper

# 构建并启动所有服务
chmod +x docker.sh
./docker.sh up

# 或者使用 docker-compose
docker-compose up -d --build
```

### 访问服务

| 服务 | URL |
|------|-----|
| 正式版前端 | http://localhost:80 |
| 正式版后端 API | http://localhost:8000 |
| 测试版前端 | http://localhost:8080 |
| 测试版后端 API | http://localhost:8030 |
| Redis 可视化 | http://localhost:8081 |

---

## 服务说明

### 启动单个服务

```bash
# 只启动正式版
docker-compose up -d backend-release worker-release frontend-release redis-release

# 只启动测试版
docker-compose up -d backend-beta worker-beta frontend-beta redis-beta
```

### 停止服务

```bash
# 停止所有
docker-compose down

# 停止测试版
docker-compose stop backend-beta worker-beta frontend-beta redis-beta
```

### 重启服务

```bash
# 重启单个服务
docker-compose restart backend-release

# 重启所有
docker-compose restart
```

---

## 数据管理

### 数据库位置

```bash
# 正式版数据库
./data/video_clipper.db

# 测试版数据库
./data/video_clipper_beta.db
```

### 备份数据库

```bash
# 使用管理脚本
./docker.sh db-backup

# 手动备份
cp data/video_clipper.db backups/video_clipper_$(date +%Y%m%d).db
cp data/video_clipper_beta.db backups/video_clipper_beta_$(date +%Y%m%d).db
```

### 恢复数据库

```bash
# 使用管理脚本
./docker.sh db-restore backups/db_backup_20260408_120000.tar.gz

# 手动恢复
cp backups/video_clipper_20260408.db data/video_clipper.db
```

### 清理数据

```bash
# 清理所有数据（慎用！）
docker-compose down -v

# 只清理测试版数据
docker volume rm video-clipper_beta_data
docker volume rm video-clipper_redis_beta_data
```

---

## 网络配置

### 查看网络

```bash
docker network ls
docker network inspect video-clipper_vc-network
```

### 容器间通信

```bash
# 后端访问 Redis
docker-compose exec backend-release redis-cli -h redis-release ping

# 前端访问后端
# 通过 nginx 代理，自动转发到 backend:8000
```

### 端口映射

| 容器端口 | 宿主机端口 | 说明 |
|---------|-----------|------|
| 80 | 80 | 正式版前端 |
| 8000 | 8000 | 正式版后端 |
| 8080 | 8080 | 测试版前端 |
| 8030 | 8030 | 测试版后端 |
| 6379 | 6379 | 正式版 Redis |
| 6379 | 6380 | 测试版 Redis |
| 8081 | 8081 | Redis 可视化 |

---

## 监控与日志

### 查看日志

```bash
# 所有服务日志
./docker.sh logs

# 单个服务日志
docker-compose logs -f backend-release

# 最近 100 行
docker-compose logs --tail=100 backend-release
```

### 查看服务状态

```bash
./docker.sh status
docker-compose ps
```

### 健康检查

```bash
# 检查所有服务健康状态
docker inspect --format='{{.Name}}: {{.State.Health.Status}}' $(docker-compose ps -q)

# 检查后端 API
curl http://localhost:8000/health
curl http://localhost:8030/health
```

### Redis 可视化

访问 http://localhost:8081 查看 Redis 数据：
- 正式版 Redis: `redis-release:6379`
- 测试版 Redis: `redis-beta:6379`

---

## 备份与恢复

### 完整备份

```bash
#!/bin/bash
# backup.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/$TIMESTAMP"

mkdir -p $BACKUP_DIR

# 备份数据库
cp data/*.db $BACKUP_DIR/

# 导出 Redis 数据
docker-compose exec redis-release redis-cli SAVE
docker-compose exec redis-beta redis-cli SAVE
cp docker-compose.yml $BACKUP_DIR/

# 打包
tar -czf backups/backup_$TIMESTAMP.tar.gz $BACKUP_DIR

echo "✅ 备份完成：backups/backup_$TIMESTAMP.tar.gz"
```

### 灾难恢复

```bash
# 1. 停止所有服务
docker-compose down

# 2. 恢复数据
tar -xzf backups/backup_20260408_120000.tar.gz -C ./

# 3. 启动服务
docker-compose up -d
```

---

## 故障排查

### 容器启动失败

```bash
# 查看容器日志
docker-compose logs backend-release

# 检查容器状态
docker-compose ps

# 重新构建
docker-compose build --no-cache backend-release

# 重新启动
docker-compose up -d backend-release
```

### 数据库连接失败

```bash
# 检查数据库文件
ls -lh data/

# 进入容器检查
docker-compose exec backend-release ls -lh /app/data/

# 检查权限
docker-compose exec backend-release chmod 666 /app/data/*.db
```

### 前端无法访问后端

```bash
# 检查 nginx 配置
docker-compose exec frontend-release cat /etc/nginx/conf.d/default.conf

# 测试后端连接
docker-compose exec frontend-release curl http://backend-release:8000/health

# 重启 nginx
docker-compose restart frontend-release
```

### Redis 连接失败

```bash
# 检查 Redis 状态
docker-compose exec redis-release redis-cli ping

# 查看 Redis 日志
docker-compose logs redis-release

# 重启 Redis
docker-compose restart redis-release
```

### Worker 不处理任务

```bash
# 查看 Worker 日志
docker-compose logs worker-release

# 检查队列长度
docker-compose exec redis-release redis-cli LLEN processing

# 重启 Worker
docker-compose restart worker-release
```

---

## 生产环境优化

### 1. 增加 Worker 并发

```yaml
# docker-compose.yml
worker-release:
  environment:
    - CELERY_CONCURRENCY=8  # 根据 CPU 核心数调整
```

### 2. 启用 Redis 持久化

```yaml
# docker-compose.yml
redis-release:
  command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

### 3. 限制容器资源

```yaml
# docker-compose.yml
backend-release:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '1.0'
        memory: 1G
```

### 4. 启用日志轮转

```yaml
# docker-compose.yml
services:
  backend-release:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 5. 使用 Docker Swarm/K8s

```bash
# Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.yml video-clipper

# Kubernetes
kubectl apply -f k8s/
```

---

## 性能调优

### FFmpeg 硬件加速

在 Docker 中启用硬件加速需要传递设备：

```yaml
# docker-compose.yml
worker-release:
  devices:
    - /dev/video0:/dev/video0  # macOS 不支持，仅 Linux
```

### 数据库优化

```python
# 启用 WAL 模式（SQLite）
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
```

### Redis 优化

```bash
# 配置 Redis 内存限制
docker-compose exec redis-release redis-cli CONFIG SET maxmemory 512mb
docker-compose exec redis-release redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

---

## 安全建议

### 1. 不要暴露 Redis 到公网

```yaml
# 移除端口映射（内部服务不需要）
redis-release:
  # ports:
  #   - "6379:6379"  # 注释掉
```

### 2. 使用环境变量管理敏感信息

```bash
# .env 文件
DATABASE_PASSWORD=your_password
SECRET_KEY=your_secret_key
```

### 3. 定期更新镜像

```bash
# 拉取最新镜像
docker-compose pull

# 重新构建
docker-compose build

# 重启服务
docker-compose up -d
```

---

## 常见问题

### Q: Docker 启动很慢？

**A:** 首次启动需要下载镜像，后续会使用缓存。可以预拉取：

```bash
docker pull python:3.11-slim
docker pull node:20-alpine
docker pull redis:7-alpine
docker pull nginx:alpine
```

### Q: 如何查看容器资源占用？

**A:**

```bash
docker stats
```

### Q: 如何在容器中调试？

**A:**

```bash
# 进入容器
docker-compose exec backend-release bash

# 查看环境变量
docker-compose exec backend-release env

# 测试 API
docker-compose exec backend-release curl http://localhost:8000/health
```

### Q: 数据卷在哪里？

**A:**

```bash
# 查看 volume
docker volume ls | grep video-clipper

# 查看 volume 位置
docker volume inspect video-clipper_release_data
```

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 正式版后端镜像 |
| `Dockerfile.frontend` | 前端生产镜像 |
| `docker-compose.yml` | 完整编排配置 |
| `docker.sh` | 管理脚本 |
| `nginx.conf` | Nginx 配置 |
| `.dockerignore` | 构建排除文件 |

---

**最后更新：** 2026-04-08  
**维护者：** 剪辑小助理 ✂️
