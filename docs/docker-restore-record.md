# Docker 恢复记录 (2026-06-16)

## 问题诊断
- **Docker 镜像为空**：`docker images` 和 `docker ps -a` 均无结果
- **build 失败原因 1**：`agents/` 目录为空（Agent 文件在 `agents_pkg/` 中）
  - 修复：`Copy-Item agents_pkg\* agents\ -Recurse`
- **build 失败原因 2**：`.dockerignore` GBK 编码乱码导致解析异常
  - 修复：重写为纯 UTF-8
- **build 被 SIGKILL 原因**：完整 `requirements.txt` 含 crewai/akshare/chromadb/lancedb/onnxruntime 等，总计 200+ 包 ~500MB，下载超时
  - 修复：精简 Dockerfile，仅安装 Dashboard+Scheduler 所需包（flask, flask-cors, flask-compress, apscheduler, pandas, python-dotenv, requests）
- **启动失败原因**：`data_fetcher.py` 顶层 `import akshare as ak` 导致 ModuleNotFoundError
  - 修复：改为惰性加载 `_AkLazy` 类，仅在调用时导入

## 当前状态
- ✅ Docker 镜像 `stock-crewai-web-dashboard:latest` (429MB) 构建成功
- ✅ 容器 `web-dashboard` 运行中，端口 5000
- ✅ Flask Dashboard 返回 200 (54,828 bytes HTML)
- ✅ `/api/health` → `{"status": "ok"}`
- ✅ `/api/scheduler_status` → `running: true`, 3个定时任务已注册
- ✅ `/api/dashboard` → 返回完整融合指标
- ✅ Scheduler 3个任务：realtime_monitor(10min), daily_analysis(9:25), performance_audit(15:05)

## 已修改文件
| 文件 | 改动 |
|------|------|
| Dockerfile | 精简依赖，只装必要包；CMD 改为 `main.py --dashboard` |
| .dockerignore | UTF-8 重写，清理乱码 |
| data_fetcher.py | `import akshare as ak` → 惰性 `_AkLazy` 加载器 |

## 关于主机 Dashboard 进程
主机上原有的 `web_dashboard.py` 进程（PID 69320）仍然运行，与 Docker 容器共用端口 5000。  
容器先启动后，主机进程可能无法绑定同一端口。  
建议：确认 Docker 容器稳定后，停掉主机进程。
