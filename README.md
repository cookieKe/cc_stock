# A股股票推荐系统 (cc_stock)

基于多策略评分的全市场股票扫描排名推荐平台。

**技术栈**: FastAPI + SQLAlchemy + akshare/tushare (后端), Vue 3 + Pinia + ECharts + Vite (前端), Podman/Docker (部署)

## 本地开发

### 环境要求

- Python 3.12+ (Anaconda: `C:\Users\cyneuzk\software\anaconda\python.exe`)
- Node.js 25+
- npm 11+

### 安装依赖

```bash
# 后端
pip install -r requirements.txt

# 前端
cd frontend && npm install
```

### 启动开发服务器

```bash
# 一键启动 (前后端同时拉起)
python start_dev.py

# 或者分别启动:
# 后端 (端口 8000)
python -m uvicorn backend.main:app --reload --port 8000

# 前端 (端口 5173, /api 代理到 localhost:8000)
cd frontend && npm run dev
```

- 前端: http://localhost:5173
- 后端: http://127.0.0.1:8000
- API 文档: http://127.0.0.1:8000/api/docs

### 运行测试

```bash
cd frontend && npm run test:unit
```

## 云服务器部署

服务器: 阿里云 8.130.149.29 (Alibaba Cloud Linux 3)

### 首次部署

```bash
# 前端需要先构建
cd frontend && npm run build

# 全量部署
python deploy_remote.py
```

部署流程: 拉取镜像 → 打包项目 → SCP上传 → 解压 → 构建后端镜像 → 启动Pod+容器

### 日常修改后快速同步

```bash
# 只改了前端代码 → 15秒 (volume mount, 无需重启容器)
python sync_remote.py frontend

# 只改了后端代码 → ~60秒 (上传 + 重建镜像 + 重启容器)
python sync_remote.py backend

# 前后端都改了
python sync_remote.py all
```

| 改动类型 | 命令 | 耗时 | 原理 |
|----------|------|------|------|
| 前端代码 | `sync_remote.py frontend` | ~15s | 本地npm build → SCP上传dist → 直接生效(volume mount) |
| 后端代码 | `sync_remote.py backend` | ~60s | SCP上传 → podman build(用层缓存) → 重启容器 |
| requirements.txt | `sync_remote.py backend` | ~90s | pip install会重新执行 |
| 首次部署 | `deploy_remote.py` | ~5min | 拉镜像+全量打包上传+构建启动 |

### 服务器信息

```bash
# SSH 连接
ssh root@8.130.149.29

# 查看服务状态
podman pod ps
podman ps --filter pod=cc-stock

# 查看日志
podman logs cc-backend
podman logs cc-postgres

# 手动重启
podman restart cc-backend
```

## 项目结构

```
cc_stock/
├── backend/
│   ├── api/              # FastAPI 路由
│   ├── data_sources/     # akshare / tushare / baostock 数据源
│   ├── models/           # SQLAlchemy 模型
│   ├── services/         # 数据同步、市场扫描
│   ├── strategy_engine/  # 策略引擎 (KDJ反转等)
│   │   ├── built_in/     # 内置策略
│   │   └── patterns/     # KDJ形态匹配图片
│   ├── config.py         # 配置 (pydantic-settings)
│   ├── database.py       # 数据库连接
│   └── main.py           # 应用入口
├── frontend/
│   └── src/
│       ├── views/        # 页面 (Scanner, StockDetail, Dashboard...)
│       ├── stores/       # Pinia 状态管理
│       ├── api/          # axios API 封装
│       └── components/   # 通用组件
├── scripts/              # 杂项脚本
├── deploy_remote.py      # 全量部署脚本
├── sync_remote.py        # 增量同步脚本
├── start_dev.py          # 本地一键启动
├── docker-compose.yml    # Docker Compose 配置
├── Dockerfile.backend    # 后端容器构建
├── Dockerfile.frontend   # 前端容器构建
└── nginx.conf            # Nginx 配置
```

## 部署架构 (服务器端)

```
Pod: cc-stock (端口 80:80, 8000:8000)
├── infra (podman-pause)              # Pod 基础设施
├── cc-postgres (postgres:16-alpine)  # PostgreSQL 数据库
├── cc-backend  (python:3.12-slim)    # FastAPI 后端 :8000
└── cc-frontend (nginx:alpine)        # 前端静态文件 :80
                                      #   /api/ → proxy → localhost:8000
```

镜像通过 DaoCloud 加速器 (`docker.m.daocloud.io`) 拉取，解决国内无法访问 Docker Hub 的问题。

## 核心功能

- **市场扫描**: 全市场多策略评分排名
- **KDJ反转策略**: 包含形态图片匹配 (Pearson相关系数)
- **股票详情**: K线/KDJ/成交量三图合一，支持滚轮缩放
- **数据同步**: Tushare批量拉取 (千倍提速)，akshare单股兜底
- **自选追踪**: 关注列表管理
- **回测验证**: 策略历史表现验证
