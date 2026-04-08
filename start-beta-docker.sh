#!/bin/bash
# 使用 Docker 启动测试版（与正式版完全隔离）

cd "$(dirname "$0")"

echo "🐳 Video Clipper 测试版（Docker 隔离模式）"
echo ""

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker"
    exit 1
fi

# 构建镜像
echo "🔨 构建 Docker 镜像..."
docker-compose -f docker-compose.beta.yml build

# 启动服务
echo ""
echo "🚀 启动测试版服务..."
docker-compose -f docker-compose.beta.yml up -d

# 等待服务启动
echo ""
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo ""
echo "📊 服务状态:"
docker-compose -f docker-compose.beta.yml ps

echo ""
echo "✅ 测试版已启动！"
echo ""
echo "访问地址："
echo "  前端：http://localhost:3030"
echo "  后端：http://localhost:8030"
echo ""
echo "数据库：data/video_clipper_beta.db"
echo "Redis:   localhost:6380 (Docker 容器内：redis:6379)"
echo ""
echo "停止服务：docker-compose -f docker-compose.beta.yml down"
echo "查看日志：docker-compose -f docker-compose.beta.yml logs -f"
