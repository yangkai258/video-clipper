# Video Clipper - 智能视频切片工具

基于 AI 的自动视频切片和合集生成工具。

## 功能特性

- ✅ 多项目管理
- ✅ 视频上传（支持 mp4/mov/avi/mkv/flv/webm）
- ✅ 自动字幕生成（bcut-asr + faster-whisper 回退）
- ✅ AI 大纲提取（DashScope Qwen）
- ✅ 智能切片生成
- ✅ 自动合集合并

## 技术栈

**后端:**
- FastAPI
- Celery + Redis
- SQLite
- faster-whisper
- DashScope

**前端:**
- React 18
- Vite
- Axios

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+
- Redis
- FFmpeg

### 2. 安装

```bash
# 克隆项目
cd /Users/zhuobao/.openclaw-rescue4/workspace/video-clipper

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 DASHSCOPE_API_KEY

# 启动后端
bash scripts/start.sh

# 新终端启动前端
bash scripts/start-frontend.sh
```

### 3. 访问

- 前端：http://localhost:3000
- API: http://localhost:8000
- API 文档：http://localhost:8000/docs

## 使用流程

1. **上传视频** - 选择视频文件，输入项目名称
2. **开始处理** - 点击"开始处理"按钮
3. **等待完成** - 自动执行字幕→大纲→切片→合集流程
4. **查看结果** - 查看生成的切片和合集

## 项目结构

```
video-clipper/
├── backend/
│   ├── api/           # API 路由
│   ├── core/          # 核心配置
│   ├── models/        # 数据库模型
│   ├── services/      # 业务服务
│   ├── tasks/         # Celery 任务
│   ├── utils/         # 工具函数
│   └── main.py        # FastAPI 入口
├── frontend/
│   ├── src/
│   │   ├── App.jsx    # 主应用
│   │   └── main.jsx   # 入口
│   └── package.json
├── data/              # 数据目录
├── scripts/           # 启动脚本
└── requirements.txt
```

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /api/v1/projects/ | 获取项目列表 |
| GET | /api/v1/projects/{id} | 获取项目详情 |
| POST | /api/v1/projects/ | 创建项目（上传视频） |
| POST | /api/v1/projects/{id}/process | 开始处理 |
| DELETE | /api/v1/projects/{id} | 删除项目 |

## 配置说明

### 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| DASHSCOPE_API_KEY | 通义千问 API Key | ✅ |
| BCUT_SESSDATA | B 站 Cookie（可选） | ❌ |
| REDIS_URL | Redis 连接 URL | ✅ |

## 故障排除

### Celery Worker 未运行

```bash
ps aux | grep celery
# 如果没有进程，重启
bash scripts/start.sh
```

### Redis 连接失败

```bash
redis-cli ping
# 应该返回 PONG
```

### 字幕生成失败

- 检查 DASHSCOPE_API_KEY 是否正确
- 检查网络连接
- 查看后端日志

## 开发

```bash
# 后端开发
source venv/bin/activate
uvicorn backend.main:app --reload

# 前端开发
cd frontend
npm run dev
```

## License

MIT
