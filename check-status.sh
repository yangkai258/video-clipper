#!/bin/bash
# Video Clipper 服务状态检查脚本

echo "========================================"
echo "  Video Clipper 服务状态检查"
echo "========================================"
echo ""

# 检查后端进程
echo "📌 后端进程检查："
ps aux | grep "uvicorn.*8000\|uvicorn.*8030" | grep -v grep | awk '{print "  ✅", $NF}' || echo "  ❌ 无后端进程运行"
echo ""

# 检查 Worker 进程
echo "📌 Worker 进程检查："
ps aux | grep "celery.*processing" | grep -v grep | head -2 | awk '{print "  ✅", $NF}' || echo "  ❌ 无 Worker 进程运行"
echo ""

# 检查前端进程
echo "📌 前端进程检查："
ps aux | grep "vite.*3000\|vite.*3030" | grep -v grep | awk '{print "  ✅", $NF}' || echo "  ❌ 无前端进程运行"
echo ""

# 检查后端健康
echo "📌 后端健康检查："
curl -s http://localhost:8000/health 2>/dev/null && echo "  ✅ 正式版 (8000) 正常" || echo "  ❌ 正式版 (8000) 异常"
curl -s http://localhost:8030/health 2>/dev/null && echo "  ✅ 测试版 (8030) 正常" || echo "  ❌ 测试版 (8030) 异常"
echo ""

# 检查数据库
echo "📌 数据库检查："
if [ -f "data/video_clipper.db" ]; then
  COUNT=$(sqlite3 data/video_clipper.db "SELECT COUNT(*) FROM projects;" 2>/dev/null)
  echo "  ✅ 正式版数据库：data/video_clipper.db ($COUNT 个项目)"
else
  echo "  ❌ 正式版数据库不存在"
fi

if [ -f "data/video_clipper_beta.db" ]; then
  COUNT=$(sqlite3 data/video_clipper_beta.db "SELECT COUNT(*) FROM projects;" 2>/dev/null)
  echo "  ✅ 测试版数据库：data/video_clipper_beta.db ($COUNT 个项目)"
else
  echo "  ⚠️  测试版数据库不存在（首次启动会自动创建）"
fi
echo ""

# 检查前端代理
echo "📌 前端代理检查："
RESULT_3000=$(curl -s http://localhost:3000/api/v1/projects/ 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['projects']))" 2>/dev/null || echo "N/A")
RESULT_3030=$(curl -s http://localhost:3030/api/v1/projects/ 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['projects']))" 2>/dev/null || echo "N/A")
echo "  正式版 (3000): $RESULT_3000 个项目"
echo "  测试版 (3030): $RESULT_3030 个项目"
echo ""

echo "========================================"
echo "  访问地址："
echo "  正式版：http://localhost:3000"
echo "  测试版：http://localhost:3030"
echo "========================================"
