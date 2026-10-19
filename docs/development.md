# 开发与验证

[返回首页](../README.md)

## 安装开发依赖

需要 Python 3.11+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## 本地检查

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m compileall -q proxyscrape_register.py proxyscrape_auth.py cloud_mail.py nodes_config.py browser_runtime.py proxy_service.py filter_xai_proxies.py
sh -n start.sh
sh -n docker-run.sh
sh -n docker-entrypoint.sh
.venv/bin/python -m build
```

自动化测试使用模拟响应或本地 HTTP 服务，不会创建真实邮箱、注册 ProxyScrape 账号或领取真实试用。覆盖配置优先级、邮箱续登与收信、注册与导出流程、已保存账号恢复、试用领取状态、分页以及启动脚本文件取回。

## 容器检查

```bash
docker compose build
docker compose run --rm nodes python tests/smoke_browser.py
docker compose run --rm nodes python tests/smoke_turnstile_dom.py
.venv/bin/python tests/smoke_container.py
```

前两个脚本在容器内打开本地测试页面，验证 Chromium、虚拟显示器、扩展加载及封闭 Shadow DOM（页面封装的组件树）中的 iframe 检测。第三个脚本在 Docker 主机运行，检查退出码和终止信号传递。这些检查均不请求 ProxyScrape 注册接口。

检查真实 Docker 输出取回可执行以下命令。它会复制 Docker 端已有的账号和节点文件，但不创建新账号：

```bash
./docker-run.sh python -c 'print("offline output copy check")'
```

## 模块职责

| 文件 | 职责 |
| --- | --- |
| `proxyscrape_register.py` | 命令行、注册与验证、账号保存、导出和恢复流程 |
| `cloud_mail.py` | Cloud Mail 登录、附属邮箱、邮件轮询和验证码识别 |
| `proxy_service.py` | 查询试用、领取试用、读取代理凭据和分页节点 |
| `browser_runtime.py` | Chrome / Chromium 启动配置 |
| `nodes_config.py` | 环境变量、`.env` 和 JSON 配置合并 |
| `docker-run.sh` | 容器运行及输出复制到本机 |

`proxyscrape_auth.py` 和 `filter_xai_proxies.py` 是保留的辅助工具，不参与默认注册流程。

## 验证范围

当前版本完成了 Linux arm64 Docker 浏览器检查、真实 Cloud Mail 登录续期检查，以及已有账号的邮箱验证状态查询、试用开通和 100 个 HTTP 代理导出。容器输出已通过真实文件复制取回 macOS 本机。

这些结果不等于所有平台和网络都已验收。Windows / macOS 完整注册流程、amd64 实机运行，以及导出代理的逐条连通性仍需在目标环境检查。试用资格、验证服务和代理数量由外部服务决定。

## 提交问题与改动

通过 [Issues](https://github.com/dnslin/nodes/issues) 描述问题，附系统架构、运行方式、版本、复现步骤和相关日志。删除真实邮箱、密码、访问凭据和带认证信息的代理 URL。

修改前阅读相关实现和测试。行为变更应补充可观察结果的测试，并运行相关检查。涉及真实邮箱、注册或试用的验证，应明确操作对象和产生的外部影响。
