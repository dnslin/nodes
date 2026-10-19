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
docker compose pull
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

这些结果不等于所有平台和网络都已验收。Windows / macOS 完整注册流程、amd64 上的真实注册业务流程，以及导出代理的逐条连通性仍需在目标环境检查。CI 的双架构检查仅验证镜像构建、容器启动和浏览器依赖能否导入。试用资格、验证服务和代理数量由外部服务决定。

## GitHub Actions 与 GHCR

工作流位于 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)。

- `main` 推送、PR、版本标签和手动运行：在 Python 3.11 / 3.12 上执行离线测试；执行 Ruff、编译、shell 语法及安装包构建检查。
- 镜像检查：分别使用 `ubuntu-24.04` 和 `ubuntu-24.04-arm` 原生构建 amd64、arm64 镜像，并运行容器命令行帮助检查。CI 不打开真实浏览器或请求注册服务。
- 版本发布：推送 `vX.Y.Z` 标签后，两个架构都通过检查才合并并发布 GHCR 标签。PR 和手动检查不会发布镜像。

GHCR 登录使用仓库自带的 `GITHUB_TOKEN`，不需要创建额外的发布密码。只有发布任务需要 `packages: write` 权限。首次发布的 GHCR 包默认是私有，仓库维护者需要在包设置中将其设为 Public；完成后用户无需登录即可拉取。

发布新版本时先修改 `pyproject.toml` 和 `CHANGELOG.md`，提交并推送到 `main`，再创建对应版本标签，例如：

```bash
git tag -a v0.1.2 -m 'Release v0.1.2'
git push origin v0.1.2
```

查看 [Actions](https://github.com/dnslin/nodes/actions/workflows/ci.yml) 结果，确认 GHCR 已发布两个架构后，再发布对应的 GitHub Release。

实现参考：[Docker 多架构构建](https://docs.docker.com/build/ci/github-actions/multi-platform/)、[GitHub Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。

## 提交问题与改动

通过 [Issues](https://github.com/dnslin/nodes/issues) 描述问题，附系统架构、运行方式、版本、复现步骤和相关日志。删除真实邮箱、密码、访问凭据和带认证信息的代理 URL。

修改前阅读相关实现和测试。行为变更应补充可观察结果的测试，并运行相关检查。涉及真实邮箱、注册或试用的验证，应明确操作对象和产生的外部影响。
