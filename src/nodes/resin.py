"""Merge exported HTTP proxies into one Resin local subscription."""

from pathlib import Path

import requests

from .console import log


def configured(config, *, required=False):
    fields = ("resin_url", "resin_admin_token")
    if not required and not any(config.get(field) for field in fields):
        return False
    missing = [field.upper() for field in fields if not config.get(field)]
    if missing:
        raise ValueError("缺少 Resin 配置: " + ", ".join(missing))
    return True


def _proxy_lines(content):
    return [line.strip() for line in content.splitlines() if line.strip()]


def _find_subscription(request, name):
    offset = 0
    matches = []
    while True:
        page = request(
            "GET", "/subscriptions", params={"keyword": name, "limit": 100, "offset": offset}
        )
        rows, total = page.get("items"), page.get("total")
        if not isinstance(rows, list) or type(total) is not int:
            raise RuntimeError("Resin 订阅列表缺少 items 数组或 total 总数")
        if any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("Resin 订阅列表包含无效记录")
        matches.extend(row for row in rows if row.get("name") == name)
        offset += len(rows)
        if offset >= total:
            break
        if not rows:
            raise RuntimeError("Resin 订阅列表分页未返回剩余记录")
    if len(matches) > 1:
        raise RuntimeError(f"Resin 中存在多个同名订阅 {name}，请先保留一个或更换订阅名")
    return matches[0] if matches else None


def sync(config, *, root=None, skip_empty=False):
    root = Path.cwd() if root is None else Path(root)
    proxies = []
    for path in sorted((root / "node").glob("proxies_*.txt")):
        proxies.extend(_proxy_lines(path.read_text(encoding="utf-8-sig")))
    if not proxies:
        if skip_empty:
            log("没有已导出的节点，未同步 Resin")
            return 0
        raise ValueError(f"在 {root / 'node'} 中没有可同步的 proxies_*.txt 节点")

    name = config.get("resin_subscription_name") or "nodes"
    base_url = config["resin_url"].rstrip("/") + "/api/v1"
    try:
        with requests.Session() as session:
            session.headers.update({"Authorization": f"Bearer {config['resin_admin_token']}"})

            def request(method, path, **kwargs):
                context = f"Resin {method} {path}"
                try:
                    response = session.request(method, base_url + path, timeout=30, **kwargs)
                except requests.RequestException as exc:
                    raise RuntimeError(f"{context} 未收到响应: {exc}") from exc
                context += f" HTTP {response.status_code}"
                try:
                    body = response.json()
                except ValueError as exc:
                    raise RuntimeError(f"{context}：响应不是 JSON") from exc
                if not isinstance(body, dict):
                    raise RuntimeError(f"{context}：响应不是 JSON 对象")
                if not response.ok:
                    error = body.get("error") or {}
                    detail = error.get("message") if isinstance(error, dict) else str(error)
                    raise RuntimeError(f"{context}：{detail or '请求失败'}")
                return body

            existing = _find_subscription(request, name)
            if existing:
                if existing.get("source_type") != "local":
                    raise RuntimeError(f"Resin 订阅 {name} 不是 local 类型，请使用专用本地订阅名")
                previous = existing.get("content")
                if not isinstance(previous, str):
                    raise RuntimeError(f"Resin 订阅 {name} 缺少文本 content")
                previous_lines = _proxy_lines(previous)
                if any(not line.startswith(("http://", "https://")) for line in previous_lines):
                    raise RuntimeError(
                        f"Resin 订阅 {name} 不是逐行 HTTP 代理文本，请更换专用订阅名"
                    )
                proxies = previous_lines + proxies
            content = "\n".join(dict.fromkeys(proxies)) + "\n"
            if existing:
                subscription_id = existing.get("id")
                if not subscription_id:
                    raise RuntimeError(f"Resin 订阅 {name} 缺少 id")
                request("PATCH", f"/subscriptions/{subscription_id}", json={"content": content})
            else:
                created = request(
                    "POST", "/subscriptions",
                    json={"name": name, "source_type": "local", "content": content},
                )
                subscription_id = created.get("id")
                if not subscription_id:
                    raise RuntimeError("Resin 创建订阅未返回 id；重试同步时会先查询同名订阅")
            request("POST", f"/subscriptions/{subscription_id}/actions/refresh")
            result = request("GET", f"/subscriptions/{subscription_id}")
            if result.get("last_error"):
                raise RuntimeError(f"Resin 订阅 {name} 刷新失败: {result['last_error']}")
            count = result.get("node_count")
            if type(count) is not int or count <= 0:
                raise RuntimeError(f"Resin 订阅 {name} 刷新后没有解析到节点，请检查订阅状态")
            log(f"Resin 订阅 {name} 已同步，当前解析节点 {count} 个（可用性由 Resin 探测）")
            return count
    except Exception as exc:
        detail = str(exc)
        token = config["resin_admin_token"]
        if token:
            detail = detail.replace(token, "***").replace(repr(token)[1:-1], "***")
        raise RuntimeError(
            f"{detail}；本地节点已保留，可修复后使用 --sync-resin 单独重试"
        ) from exc
