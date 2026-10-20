# Nodes

使用 Cloud Mail 完成 ProxyScrape 注册、邮箱验证与 HTTP 代理导出，支持 Linux 和 Docker。

[![CI](https://github.com/dnslin/nodes/actions/workflows/ci.yml/badge.svg)](https://github.com/dnslin/nodes/actions/workflows/ci.yml)
[![GHCR](https://img.shields.io/badge/GHCR-amd64%20%7C%20arm64-2496ED?logo=docker&logoColor=white)](https://github.com/dnslin/nodes/pkgs/container/nodes)

- **开箱运行**：镜像内置 Chromium 和虚拟显示器，本机无需安装 Python。
- **自动取回文件**：运行结束后，账号与节点保存到本机项目目录。
- **继续已有账号**：导出失败后可复用已保存账号，无需重新注册。

## 快速开始

需要 Docker、Docker Compose 和 POSIX shell；Windows 推荐使用 WSL。邮箱需为可创建附属邮箱的 **Cloud Mail 3.0.0** 账号。

```bash
git clone https://github.com/dnslin/nodes.git
cd nodes
cp .env.example .env
```

编辑 `.env`，填写邮箱站点和登录信息。站点地址不包含 `/api`：

```dotenv
CLOUD_MAIL_URL=https://mail.example.org
CLOUD_MAIL_EMAIL=owner@example.org
CLOUD_MAIL_PASSWORD="你的登录密码"
```

拉取镜像，检查邮箱，再运行一个任务：

```bash
docker compose pull
./scripts/run-docker.sh --check-mail
./scripts/run-docker.sh --count 1 --threads 1 --attempts 1 --hide-browser
```

默认镜像为 `ghcr.io/dnslin/nodes:latest`，自动选择 amd64 或 arm64。上面的注册命令只尝试一次；试用资格、代理数量和验证服务是否接受请求由服务端决定。

## 取出节点与恢复

脚本自动取回输出，无需进入容器：

```text
account/accounts_*.jsonl   账号、访问凭据与处理结果
node/proxies_*.txt         HTTP 代理，每行一个地址
```

账号已注册且邮箱已验证时，可继续处理试用和导出：

```bash
./scripts/run-docker.sh --resume saved@example.org
```

请妥善保存 `.env` 和账号文件。复制失败时，脚本保留容器并显示手动取回命令。导出成功不代表每个代理都已通过连通性检查。

## 文档

- [使用指南](docs/usage.md)：配置、Linux / macOS / Windows、本地构建、参数与常见问题。
- [开发指南](docs/development.md)：目录结构、测试和 GitHub Actions / GHCR 发布。
- [更新记录](CHANGELOG.md) · [问题反馈](https://github.com/dnslin/nodes/issues)

## 来源与授权

基于 [kingenbomb/Nodes](https://github.com/kingenbomb/Nodes/tree/1216835354d0c68b768b59ce137b75f40fe3e9ac) 改造，作为独立仓库维护。上游未声明许可证，本仓库暂未声明统一开源许可证，保留原作者权利。使用时请遵守相关服务条款，仅操作有权使用的账号。
