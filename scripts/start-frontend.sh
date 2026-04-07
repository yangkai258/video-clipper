#!/bin/bash

# 前端启动脚本

set -e

echo "🎨 启动前端开发服务器..."

cd frontend

# 安装依赖
if [ ! -d "node_modules" ]; then
    echo "📦 安装 npm 依赖..."
    npm install
fi

# 启动开发服务器
echo "🚀 启动 Vite 开发服务器..."
npm run dev
