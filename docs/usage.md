# 使用指南

[返回首页](../README.md)

## 配置

配置优先级为：**进程环境变量 > `.env` > `config.local.json`**。相对路径以项目目录为基准。使用 JSON 时，复制 `config.local.json.example` 后编辑。

JSON 配置适用于本机 Python 运行。默认 Docker 配置不会复制或挂载 `config.local.json`，请通过 `.env` 配置容器。

| 环境变量 | JSON 字段 | 含义 |
| --- | --- | --- |
| `CLOUD_MAIL_URL` | `cloud_mail_url` | Cloud Mail 3.0.0 站点地址，不包含 `/api` |
| `CLOUD_MAIL_EMAIL` | `cloud_mail_email` | 有权创建附属邮箱的登录邮箱 |
| `CLOUD_MAIL_PASSWORD` | `cloud_mail_password` | 登录密码 |
| `BROWSER_PATH` | `browser_path` | 可选，Chrome / Chromium 可执行文件路径 |
| `TURNSTILE_EXTENSION_PATH` | `turnstile_extension_path` | 可选，扩展目录，默认使用项目的 `turnstilePatch/` |

Docker 镜像已配置 `/usr/bin/chromium`，一般不需要指定浏览器路径。不要把宿主机的 macOS 或 Windows 浏览器路径传入 Linux 容器。

Cloud Mail 客户端共用本轮登录状态，邮箱 HTTP 请求依次执行，浏览器任务仍可并发。只有明确的 HTTP 401 或 API `code: 401` 才触发一次重新登录。网络错误、权限错误、登录失败或第二次 401 会直接报告。

新邮箱使用站点返回的第一个可用域名。收信只处理本轮邮箱中新增、收件人匹配且发件人来自 ProxyScrape 域名的邮件。

## Docker

```bash
# 首次运行或更新代码后构建镜像
docker compose build

# 检查邮箱，不创建账号
./docker-run.sh --check-mail

# 一个任务，只尝试一次
./docker-run.sh --count 1 --threads 1 --attempts 1 --hide-browser

# 继续已保存且邮箱已验证的账号
./docker-run.sh --resume saved@example.org

# 查看全部参数
./docker-run.sh --help
```

`docker-run.sh` 会转发参数，等待容器结束，然后将账号和节点复制到运行脚本的本机项目目录。输出先复制到临时目录，再写入本机目录，以免 Docker 共享同一目录时边读边覆盖文件。

复制完成后删除本次运行容器，并保留原任务退出码。复制失败时不删除容器，终端会显示容器名、临时目录和手动取回命令。例如，将日志里的实际容器名替换到下方：

```bash
docker cp CONTAINER_NAME:/app/node/. ./node/
docker cp CONTAINER_NAME:/app/account/. ./account/
```

不要在取回文件前删除保留的容器。Compose 的绑定目录属于 Docker 所在主机；在 Colima 或远程 Docker 下，它可能与本机项目目录不同。将本机备份迁移到其他 Docker 主机后，需要先将账号文件放入该主机映射的 `account/` 目录，`--resume` 才能读取。

容器使用 Chromium 和 Xvfb，无需宿主机桌面。Dockerfile 使用 Debian Chromium 包，可用于 amd64 和 arm64；当前真实容器运行验证在 Linux arm64 上完成，amd64 尚未实机验证。

## Linux 本机

按[首页](../README.md#linux-直接运行)安装依赖、配置邮箱后：

```bash
./start.sh --count 1 --threads 1 --attempts 1 --hide-browser
./start.sh --resume saved@example.org
```

Linux 没有 `DISPLAY` 时，`start.sh` 自动调用 `xvfb-run`。有桌面的 Linux 可以使用 `--show-browser`。在 Xvfb 中，该参数只会把窗口显示在虚拟显示器中。

如果 Chromium 由 Snap 安装或位于非标准路径，可配置 `BROWSER_PATH` 指向实际可执行文件。

## macOS 与 Windows 本机

需要 Python 3.11+ 和 Chrome。先安装依赖并配置 `.env`：

```bash
python -m pip install -r requirements.txt
python proxyscrape_register.py --check-mail
python proxyscrape_register.py --count 1 --threads 1 --attempts 1 --show-browser
```

macOS 可使用 `./start.sh`；Windows 可使用 `start.bat`。Windows 启动脚本会优先使用 `.venv\Scripts\python.exe`。Docker 启动脚本需要 POSIX shell，Windows 推荐使用 WSL。

在可交互终端中，不带参数运行 `python proxyscrape_register.py` 会进入菜单。非交互环境必须指定 `--count`、`--resume` 或 `--check-mail`。macOS 和 Windows 完整注册流程尚未实机验收。

## 命令参数

| 参数 | 作用 | 默认值 |
| --- | --- | --- |
| `--count N` | 本轮任务数，失败任务可能按 `--attempts` 使用新邮箱重试 | 交互菜单输入 |
| `--resume EMAIL` | 继续该邮箱已保存账号的试用处理和代理导出，只执行一次 | 关闭 |
| `--check-mail` | 登录 Cloud Mail 并读取主邮箱邮件列表 | 关闭 |
| `--threads N` | 并发数，实际不超过任务数和 8 | 3 |
| `--attempts N` | 每个任务最多尝试次数 | 3 |
| `--hide-browser` | 隐藏浏览器窗口 | 开启 |
| `--show-browser` | 显示浏览器窗口 | 关闭 |
| `--mail-timeout N` | 等待新验证邮件的秒数 | 180 |
| `--challenge-timeout N` | 浏览器验证超时秒数 | 120 |

`--count`、`--resume`、`--check-mail` 互斥。`--resume` 不使用邮箱配置、浏览器或 `--attempts`；它要求已保存的 ProxyScrape 访问凭据仍然有效。

一轮命令行任务结束后退出。全部任务导出成功返回 0；存在未完成任务返回 1；参数错误返回 2；程序捕获到键盘中断时返回 130。

## 文件与恢复

| 文件 | 内容 |
| --- | --- |
| `account/accounts_*.jsonl` | 每行一份账号记录，包含登录和代理凭据、验证状态、导出数量以及错误信息 |
| `node/proxies_*.txt` | 本轮成功导出的 HTTP 代理，每行一个地址 |
| `node/proxies_resume_*.txt` | 继续已有账号后生成的新代理文件 |

每轮注册使用独立的时间戳文件。已完成注册的账号即使后续失败也会保存。`--resume` 从账号文件中查找该邮箱最新记录，处理结果追加到原文件，保留原记录。

只有服务端确认 `EmailVerified: true` 后才会处理试用。尚未领取时提交一次领取请求；已经领取时从套餐概览中识别试用子账号，不选择付费子账号替代。服务端拒绝、套餐过期或代理列表暂不可用时，命令会报错。可以根据错误修复后，再对同一账号执行 `--resume`。

如果领取请求发出后没有收到响应，不会立即重复提交。再次 `--resume` 时会先重新查询领取状态。

## 可选的代理检查

仓库保留 `filter_xai_proxies.py`。它默认读取最新代理文件，并尝试访问 xAI 登录页面；这只说明该次请求的结果，不能代表所有目标站点均可使用。

```bash
.venv/bin/python filter_xai_proxies.py --help
# --url 可改为你有权测试的目标；下面仅检查前 3 个代理。
.venv/bin/python filter_xai_proxies.py --limit 3 --workers 1 --url https://example.com
```

该工具会请求真实目标，并在日志中输出代理地址和认证凭据。分享日志前请删除凭据。

## 更新

```bash
git pull --ff-only
docker compose build
```

本机直接运行时，在更新后重新安装 `requirements.txt`。保留 `.env`、`account/` 和 `node/`，不要把它们当作可删除的构建缓存。
