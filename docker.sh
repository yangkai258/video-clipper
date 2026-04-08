#!/bin/bash
# Video Clipper Docker 管理脚本

set -e

COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="video-clipper"

show_help() {
    cat << EOF
🐳 Video Clipper Docker 管理工具

用法：$0 <命令> [选项]

命令:
  up          启动所有服务
  down        停止所有服务
  restart     重启所有服务
  status      查看服务状态
  logs        查看日志
  build       构建镜像
  clean       清理所有容器和镜像
  shell       进入容器 shell
  db-backup   备份数据库
  db-restore  恢复数据库

选项:
  --release   只操作正式版
  --beta      只操作测试版
  --all       操作所有版本（默认）
  -f, --file  指定 docker-compose 文件

示例:
  $0 up                    # 启动所有服务
  $0 logs --release        # 查看正式版日志
  $0 shell backend-beta    # 进入测试版后端容器
  $0 db-backup             # 备份数据库

EOF
}

# 解析参数
RELEASE_ONLY=false
BETA_ONLY=false
SERVICES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --release)
            RELEASE_ONLY=true
            shift
            ;;
        --beta)
            BETA_ONLY=true
            shift
            ;;
        --all)
            RELEASE_ONLY=false
            BETA_ONLY=false
            shift
            ;;
        -f|--file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        *)
            SERVICES="$SERVICES $1"
            shift
            ;;
    esac
done

# 构建服务列表
if [ "$RELEASE_ONLY" = true ]; then
    SERVICES="$SERVICES backend-release worker-release frontend-release redis-release"
elif [ "$BETA_ONLY" = true ]; then
    SERVICES="$SERVICES backend-beta worker-beta frontend-beta redis-beta"
fi

# 执行命令
case $1 in
    up)
        echo "🚀 启动服务..."
        if [ -n "$SERVICES" ]; then
            docker-compose -f $COMPOSE_FILE up -d $SERVICES
        else
            docker-compose -f $COMPOSE_FILE up -d
        fi
        echo ""
        echo "✅ 服务已启动！"
        echo ""
        echo "访问地址："
        echo "  正式版前端：http://localhost:80"
        echo "  正式版后端：http://localhost:8000"
        echo "  测试版前端：http://localhost:8080"
        echo "  测试版后端：http://localhost:8030"
        echo "  Redis 可视化：http://localhost:8081"
        ;;
    
    down)
        echo "🛑 停止服务..."
        docker-compose -f $COMPOSE_FILE down
        echo "✅ 服务已停止"
        ;;
    
    restart)
        echo "🔄 重启服务..."
        docker-compose -f $COMPOSE_FILE restart
        ;;
    
    status)
        echo "📊 服务状态:"
        echo ""
        docker-compose -f $COMPOSE_FILE ps
        ;;
    
    logs)
        echo "📋 查看日志..."
        if [ -n "$SERVICES" ]; then
            docker-compose -f $COMPOSE_FILE logs -f $SERVICES
        else
            docker-compose -f $COMPOSE_FILE logs -f
        fi
        ;;
    
    build)
        echo "🔨 构建镜像..."
        docker-compose -f $COMPOSE_FILE build --no-cache
        ;;
    
    clean)
        echo "🧹 清理所有容器和镜像..."
        docker-compose -f $COMPOSE_FILE down -v --rmi all
        docker system prune -f
        echo "✅ 清理完成"
        ;;
    
    shell)
        CONTAINER=$2
        if [ -z "$CONTAINER" ]; then
            echo "❌ 请指定容器名：backend-release, backend-beta, worker-release, worker-beta"
            exit 1
        fi
        echo "🔧 进入容器：$CONTAINER"
        docker-compose -f $COMPOSE_FILE exec $CONTAINER sh
        ;;
    
    db-backup)
        echo "💾 备份数据库..."
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        mkdir -p backups
        cp data/*.db backups/ || true
        tar -czf backups/db_backup_$TIMESTAMP.tar.gz data/
        echo "✅ 数据库已备份到 backups/db_backup_$TIMESTAMP.tar.gz"
        ;;
    
    db-restore)
        BACKUP_FILE=$2
        if [ -z "$BACKUP_FILE" ]; then
            echo "❌ 请指定备份文件"
            ls -la backups/
            exit 1
        fi
        echo "🔄 恢复数据库..."
        tar -xzf $BACKUP_FILE -C ./
        echo "✅ 数据库已恢复"
        ;;
    
    ps)
        docker-compose -f $COMPOSE_FILE ps
        ;;
    
    *)
        show_help
        ;;
esac
