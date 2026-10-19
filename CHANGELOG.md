# 更新记录

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
