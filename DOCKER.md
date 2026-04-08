# Video Clipper Docker 部署指南

**最后更新：** 2026-04-08

---

## 🎯 为什么使用 Docker？

### 当前问题（非 Docker 方案）

1. **缓存污染**：Git 分支切换时 `node_modules/.vite` 缓存不会自动清除
2. **配置混乱**：两个版本共享依赖，配置容易互相覆盖
3. **数据库风险**：手动操作可能误用正式数据库
4. **环境不一致**：开发环境和生产环境可能有差异

### Docker 方案优势

1. **完全隔离**：测试版在容器内，与宿主机完全独立
2. **独立依赖**：每个版本有自己的 `node_modules`
3. **独立数据库**：Docker volume 管理，不会误用
4. **独立网络**：端口映射清晰，不会冲突
5. **一键清理**：`docker down` 就干净了
6. **环境一致**：容器内环境完全可复现

---

## 📋 架构对比

### 非 Docker 方案（当前）

```
宿主机
├─ 正式版 (3000/8000) ──┐
│   ├─ node_modules      │ 共享依赖，缓存污染
│   └─ data/             │ 共享数据目录
└─ 测试版 (3030/8030) ──┘
```

### Docker 方案（推荐）

```
宿主机
└─ 正式版 (3000/8000)
    ├─ node_modules (独立)
    └─ data/video_clipper.db

Docker 容器
└─ 测试版 (3030/8030)
    ├─ node_modules (容器内独立)
    ├─ data/video_clipper_beta.db (volume 挂载)
    └─ Redis 6380 (容器内 6379)
```

---

## 🚀 快速开始

### 前置条件

```bash
# 安装 Docker Desktop (macOS)
# https://www.docker.com/products/docker-desktop/

# 验证 Docker 安装
docker --version
docker-compose --version
```

### 启动测试版（Docker）

```bash
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper

# 一键启动测试版（Docker 隔离模式）
./start-beta-docker.sh
```

### 启动正式版（宿主机）

```bash
# 正式版继续在宿主机运行
./start-release.sh
```

---

## 🔧 常用命令

### 查看服务状态

```bash
docker-compose -f docker-compose.beta.yml ps
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.beta.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.beta.yml logs backend
docker-compose -f docker-compose.beta.yml logs frontend
docker-compose -f docker-compose.beta.yml logs worker
```

### 重启服务

```bash
# 重启所有服务
docker-compose -f docker-compose.beta.yml restart

# 重启特定服务
docker-compose -f docker-compose.beta.yml restart backend
```

### 停止服务

```bash
# 停止并保留数据
docker-compose -f docker-compose.beta.yml down

# 停止并删除数据（慎用！）
docker-compose -f docker-compose.beta.yml down -v
```

### 进入容器

```bash
# 进入后端容器
docker-compose -f docker-compose.beta.yml exec backend sh

# 进入前端容器
docker-compose -f docker-compose.beta.yml exec frontend sh

# 进入 Redis 容器
docker-compose -f docker-compose.beta.yml exec redis redis-cli
```

---

## 📁 数据持久化

### 数据库

测试版数据库文件位置：
```
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/data/video_clipper_beta.db
```

通过 Docker volume 挂载到容器内，容器删除后数据不会丢失。

### Redis

Redis 数据存储在 Docker volume 中：
```bash
# 查看 volume
docker volume ls | grep video_clipper

# 查看 volume 详情
docker volume inspect video-clipper_redis_beta_data
```

---

## 🎯 使用场景

### 场景 1：日常开发测试

```bash
# 宿主机运行正式版
./start-release.sh

# Docker 运行测试版
./start-beta-docker.sh
```

**优点：** 两个版本完全隔离，不会互相影响

### 场景 2：测试新功能

```bash
# 在 main 分支开发新功能
git checkout main
# ... 开发 ...

# 用 Docker 测试
./start-beta-docker.sh

# 测试完成后清理
docker-compose -f docker-compose.beta.yml down
```

**优点：** 测试环境用完即弃，不会污染宿主机

### 场景 3：多版本并行测试

```bash
# 启动多个测试版本（不同端口）
docker-compose -f docker-compose.beta.yml up -d
# 修改 docker-compose 端口为 3031/8031
docker-compose -f docker-compose.beta.v2.yml up -d
```

**优点：** 可以同时测试多个版本

---

## 🔍 故障排查

### 容器启动失败

```bash
# 查看容器日志
docker-compose -f docker-compose.beta.yml logs

# 检查端口占用
lsof -i :3030
lsof -i :8030
lsof -i :6380

# 重建容器
docker-compose -f docker-compose.beta.yml down
docker-compose -f docker-compose.beta.yml build --no-cache
docker-compose -f docker-compose.beta.yml up -d
```

### 数据库连接失败

```bash
# 检查数据库文件
ls -lh data/video_clipper_beta.db

# 进入容器检查
docker-compose -f docker-compose.beta.yml exec backend ls -lh /app/data/
```

### 前端无法访问后端

```bash
# 检查后端健康状态
curl http://localhost:8030/health

# 检查容器网络
docker-compose -f docker-compose.beta.yml exec backend ping redis
```

---

## 📊 性能对比

| 项目 | 非 Docker | Docker |
|------|----------|--------|
| 启动速度 | 快（~5 秒） | 中等（~15 秒） |
| 内存占用 | 低 | 中等（+200MB） |
| 磁盘占用 | 低 | 中等（+500MB 镜像） |
| 隔离性 | 差 | 完全隔离 |
| 稳定性 | 易受污染 | 稳定 |
| 清理难度 | 手动 | 一键 |

---

## 🎓 最佳实践

### ✅ 应该做的

1. **测试版始终用 Docker**：避免缓存污染
2. **正式版用宿主机**：性能最优
3. **定期清理镜像**：`docker image prune`
4. **使用 volume 管理数据**：不要直接修改容器内文件

### ❌ 不应该做的

1. **不要在容器和宿主机之间切换运行测试版**
2. **不要手动修改容器内的配置文件**
3. **不要删除 Docker volume（除非要清空测试数据）**
4. **不要在生产环境使用 Docker 开发模式**

---

## 📚 相关文件

| 文件 | 用途 |
|------|------|
| `Dockerfile.beta` | 测试版后端镜像 |
| `Dockerfile.frontend.beta` | 测试版前端镜像 |
| `docker-compose.beta.yml` | Docker Compose 配置 |
| `start-beta-docker.sh` | 一键启动脚本 |

---

## 🆘 常见问题

### Q: Docker 启动很慢？

**A:** 首次启动需要下载镜像，后续会使用缓存。可以预拉取镜像：

```bash
docker pull node:20-alpine
docker pull redis:7-alpine
```

### Q: 容器内文件修改会同步到宿主机吗？

**A:** 通过 volume 挂载的目录会同步（如 `data/`），但容器内的 `node_modules` 不会。

### Q: 如何彻底清理测试环境？

**A:** 

```bash
# 停止并删除容器
docker-compose -f docker-compose.beta.yml down

# 删除 volume（会丢失测试数据）
docker-compose -f docker-compose.beta.yml down -v

# 删除镜像
docker rmi video-clipper-backend
docker rmi video-clipper-frontend
```

### Q: 可以在 Docker 中运行正式版吗？

**A:** 可以，但不推荐。正式版需要高性能和稳定性，建议直接在宿主机运行。

---

**最后更新：** 2026-04-08  
**维护者：** 剪辑小助理 ✂️
