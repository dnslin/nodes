# 更新记录

## 0.2.0 — 2026-10-20

### 调整

- 应用迁入标准的 `src/nodes/` 包，分离命令行、业务流程、HTTP 接口、浏览器、邮箱和文件存储。
- 本地入口统一为安装后的 `nodes` 命令，也支持 `python -m nodes`。
- 删除 `start.sh`、`start.bat` 和项目自定义的容器入口脚本。仅保留 `scripts/run-docker.sh`，Docker 用户无需在本机安装 Python。
- 依赖和构建配置统一到 `pyproject.toml`，移除重复的 requirements 文件。浏览器扩展随安装包分发。
- 单元、集成和运行检查分别放入 `tests/unit/`、`tests/integration/`、`tests/smoke/`，辅助工具移入 `tools/`。
- Docker 镜像安装应用包，不包含仓库测试和文档源码。CI 同步验证安装后的标准命令。
- Docker 默认停止信号使用 `SIGINT`，与命令行中断一致，避免虚拟显示器的父进程先退出而截断应用清理。

### 使用方式变更

- `./docker-run.sh ...` 改为 `./scripts/run-docker.sh ...`。
- 本地运行先安装项目，再执行 `.venv/bin/nodes ...`；Windows 使用 `.venv\Scripts\nodes.exe ...`。
- 本地配置和 `account/`、`node/` 均以当前工作目录为准。已有文件无需转换；在原项目目录运行即可继续读取。
- 直接使用 `docker run` 时，命令中需要写出程序名，例如 `docker run --rm ghcr.io/dnslin/nodes:0.2.0 nodes --help`。通过 Docker 启动脚本运行时仍只传业务参数。

## 0.1.1 — 2026-10-20

### 新增

- GitHub Actions 自动运行 Python 3.11 / 3.12 离线测试、静态检查及安装包构建。
- amd64、arm64 原生镜像构建和容器启动检查，版本标签通过检查后自动发布到 GHCR。
- 多架构镜像的完整版本、次版本和 `latest` 标签。

### 调整

- Docker 默认拉取 `ghcr.io/dnslin/nodes:latest`，通过 `NODES_IMAGE` 选择固定版本或本地构建镜像。
- README 补充镜像拉取、版本选择、更新和自动发布说明。

## 0.1.0 — 2026-10-20

首次作为独立仓库发布。

### 新增

- Cloud Mail 3.0.0 登录、附属邮箱创建、验证邮件识别及会话失效后的单次重新登录。
- Docker 与 Linux 服务器启动方式，容器内置 Chromium 和虚拟显示器。
- `--resume EMAIL`，继续处理已保存账号的试用和代理导出。
- `docker-run.sh`，运行结束后把账号和节点取回本机目录。
- 离线自动化测试、浏览器检查，以及完整使用和开发文档。

### 修复

- 检测封闭 Shadow DOM 内的原生 Turnstile iframe，避免因漏查而重复创建验证组件。
- 注册后按服务端状态开通或复用试用，不再依赖注册响应中的子账号快照。
- 按 JSON 接口分页读取代理，正确编码代理认证凭据。

### 调整

- 邮箱服务替换为 Cloud Mail，移除 YYDS 邮箱依赖。
- 当前项目不再提供旧版 `proxyscrape run/register` 命令和 FlareSolverr 服务。
