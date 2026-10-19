# Nodes

**使用 Cloud Mail 完成 ProxyScrape 注册、邮箱验证与 HTTP 代理导出。**

支持 Docker 和 Linux 服务器。任务结束后，账号与节点直接保存到本机目录；导出失败时，可以继续处理已保存的账号。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-supported-2496ED?logo=docker&logoColor=white)
![Cloud Mail](https://img.shields.io/badge/Cloud%20Mail-3.0.0-438A65)

[快速开始](#快速开始) · [取出节点](#取出节点) · [继续已有账号](#继续已有账号) · [使用文档](docs/usage.md) · [问题反馈](https://github.com/dnslin/nodes/issues)

## 能做什么

- **Cloud Mail 收信**：创建附属邮箱，识别新收到的 ProxyScrape 验证邮件。邮箱登录失效时，重新登录一次并继续当前请求。
- **完整处理流程**：浏览器验证 → 注册 → 验证邮箱 → 查询或领取当前账号试用 → 分页导出 HTTP 代理。
- **服务器运行**：Docker 包含 Chromium 和虚拟显示器，无需安装桌面环境。
- **本机文件交付**：启动脚本自动取回容器输出，适用于 Linux、Docker Desktop、Colima 和远程 Docker。
- **失败后继续**：通过 `--resume EMAIL` 复用已保存账号，不必重新注册或再次收取验证码。

代理数量、试用资格、有效期和目标站点可用性由服务端决定。成功导出表示已取得代理配置，不代表每个代理都已通过连通性检查。

## 快速开始

推荐使用 Docker。需要 Docker Engine / Docker Desktop、Docker Compose，以及可执行 shell 脚本的终端。Windows 用户可在 WSL 中使用此方式。

### 1. 下载项目

```bash
git clone https://github.com/dnslin/nodes.git
cd nodes
cp .env.example .env
```

### 2. 配置邮箱

编辑 `.env`，填写可登录 **Cloud Mail 3.0.0** 的账号。该账号需要具备创建附属邮箱的权限，站点需要配置可用邮箱域名。

```dotenv
CLOUD_MAIL_URL=https://mail.example.org
CLOUD_MAIL_EMAIL=owner@example.org
CLOUD_MAIL_PASSWORD="你的登录密码"
```

`CLOUD_MAIL_URL` 填站点地址，不要附加 `/api`。密码包含 `#` 等字符时使用引号。其余配置先保留默认值。

### 3. 构建并检查邮箱

```bash
docker compose build
./docker-run.sh --check-mail
```

看到 `Cloud Mail 接口正常` 后再继续。此检查只读取主邮箱邮件列表，不创建邮箱，也不注册 ProxyScrape 账号。

### 4. 运行一个任务

```bash
./docker-run.sh --count 1 --threads 1 --attempts 1 --hide-browser
```

此命令只尝试一次。成功后会显示导出的代理数量，以及本机 `account/`、`node/` 的完整路径。

> `--count` 是任务数。`--attempts` 默认值为 3，失败重试会使用新邮箱。首次运行建议保留上面的 `--attempts 1`；处理已注册账号时使用下面的 `--resume`。

## 取出节点

**使用 `docker-run.sh` 后，直接在运行命令的本机项目目录中找文件：**

```text
nodes/
├── account/
│   └── accounts_<时间戳>.jsonl
└── node/
    ├── proxies_<时间戳>.txt
    └── proxies_resume_<时间戳>.txt
```

代理文件每行一个地址，可复制到支持 HTTP 代理认证的客户端。下面是格式示例，地址和凭据均为占位内容：

```text
http://username:password@192.0.2.10:8080
```

账号文件记录邮箱、密码、访问凭据、验证状态和导出结果。请妥善保存；`.env`、`account/`、`node/` 均已排除在 Git 跟踪范围外。

脚本会先取回文件，再删除运行容器。任务失败时仍会取回已保存的账号。复制失败时，容器会保留，终端会给出手动取出命令。直接使用 `docker compose run --rm` 时，目录是否出现在本机取决于 Docker 的文件共享配置。

## 继续已有账号

如果注册成功、邮箱已验证，但领取试用或导出失败，用账号文件里的邮箱继续：

```bash
./docker-run.sh --resume saved@example.org
```

程序查询当前账号的真实状态：尚未领取试用时提交领取请求一次，已经领取时读取试用子账号并导出。它不会创建新邮箱或注册新账号，也不会打开浏览器。访问凭据仍需有效，邮箱也必须已经通过服务端验证。

成功后生成新的 `proxies_resume_*.txt`，处理结果追加到原账号文件。服务端拒绝领取或套餐已过期时，会保留错误原因。

## Linux 直接运行

需要 Python 3.11+ 和 Chromium。Debian / Ubuntu 可按以下方式安装：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv chromium xvfb xauth
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./start.sh --check-mail
./start.sh --count 1 --threads 1 --attempts 1 --hide-browser
```

同样需要先配置 `.env`。没有桌面时，`start.sh` 自动通过 Xvfb 提供虚拟显示器。浏览器路径、macOS 和 Windows 本地运行方法见[使用文档](docs/usage.md)。

## 常见问题

**Docker 运行成功，本机没有节点文件？**

请通过 `./docker-run.sh ...` 运行。它使用 Docker 文件复制接口取回输出，不依赖项目目录是否共享给 Docker 虚拟机。看到“节点已保存到”后，打开对应的本机路径。

**Cloud Mail 返回 401？**

程序会重新登录并重试当前邮箱请求一次。如果仍失败，检查 `.env` 中的登录账号和密码，以及站点是否允许该账号调用接口。完整错误会保留请求方法和接口路径。

**提示缺少子账号或没有代理？**

注册响应不一定包含试用子账号。本项目会查询试用状态；已保存的账号使用 `--resume EMAIL`。不要为了重试导出重复执行新账号注册命令。

**Turnstile 验证超时？**

先查看日志里的输入框、验证 iframe 和验证凭据状态，再确认当前网络能访问目标站点及验证服务。超时不代表注册成功；本项目不保证验证服务在所有网络环境中都接受请求。

## 文档与开发

- [完整使用指南](docs/usage.md)：配置、命令参数、运行平台、更新和故障恢复。
- [开发与验证](docs/development.md)：依赖安装、离线测试、浏览器检查和验证范围。
- [更新记录](CHANGELOG.md)：发布版本与用户可见变化。
- [提交问题](https://github.com/dnslin/nodes/issues)：请附运行方式、版本和去除凭据后的日志。

## 项目来源与授权

Nodes 作为独立仓库维护，最初基于 [kingenbomb/Nodes](https://github.com/kingenbomb/Nodes/tree/1216835354d0c68b768b59ce137b75f40fe3e9ac) 改造。当前版本新增 Cloud Mail 接入、Linux / Docker 运行、账号恢复、试用状态处理和本机文件取回。

感谢上游项目及 [DrissionPage](https://github.com/g1879/DrissionPage)、[Requests](https://github.com/psf/requests)、[python-dotenv](https://github.com/theskumar/python-dotenv) 等依赖。上游未声明许可证，本仓库暂未声明统一开源许可证，保留原作者权利。

使用时应遵守 ProxyScrape 和邮箱服务的使用条款，并仅操作你有权使用的账号。
