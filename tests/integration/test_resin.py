"""Verify Resin synchronization against a real, offline localhost HTTP service."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from nodes import resin

PROXY_A = "http://account-a:secret@127.0.0.1:8000"
PROXY_B = "http://account-b:secret@127.0.0.2:8001"
PROXY_OLD = "http://old-account:secret@127.0.0.3:8002"


@pytest.fixture
def resin_server():
    state = {
        "subscriptions": [],
        "requests": [],
        "create_count": 0,
        "unauthorized": False,
        "refresh_error": "",
        "drop_create_response": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def do_PATCH(self):
            self.dispatch()

        def respond(self, result, status=200):
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def dispatch(self):
            url = urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            payload = json.loads(body) if body else None
            query = parse_qs(url.query)
            state["requests"].append(
                (self.command, url.path, query, payload, self.headers.get("Authorization"))
            )
            if state["unauthorized"] or self.headers.get("Authorization") != "Bearer test-admin":
                self.respond({"error": {"message": "invalid admin token"}}, 401)
                return
            collection = "/api/v1/subscriptions"
            if url.path == collection:
                if self.command == "GET":
                    keyword = query.get("keyword", [""])[0]
                    rows = [row for row in state["subscriptions"] if keyword in row["name"]]
                    offset, limit = int(query["offset"][0]), int(query["limit"][0])
                    self.respond({"items": rows[offset:offset + limit], "total": len(rows)})
                    return
                if self.command == "POST":
                    state["create_count"] += 1
                    row = {
                        **payload,
                        "id": f"created-{state['create_count']}",
                        "last_error": "",
                        "node_count": 0,
                    }
                    state["subscriptions"].append(row)
                    if state["drop_create_response"]:
                        state["drop_create_response"] = False
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        self.close_connection = True
                        return
                    self.respond(row, 201)
                    return
            if url.path.startswith(collection + "/"):
                subscription_id = url.path[len(collection) + 1:].split("/")[0]
                row = next(
                    (row for row in state["subscriptions"] if row["id"] == subscription_id), None
                )
                if row is not None:
                    if self.command == "PATCH":
                        row.update(payload)
                    elif self.command == "POST" and url.path.endswith("/actions/refresh"):
                        row["last_error"] = state["refresh_error"]
                        row["node_count"] = (
                            0 if row["last_error"] else len(row["content"].splitlines())
                        )
                        self.respond({"status": "ok"})
                        return
                    self.respond(row)
                    return
            self.respond({"error": {"message": "unknown endpoint"}}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = {
        "resin_url": f"http://127.0.0.1:{server.server_port}",
        "resin_admin_token": "test-admin",
        "resin_subscription_name": "nodes-dedicated",
    }
    try:
        yield config, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def export(root, name, *proxies):
    directory = root / "node"
    directory.mkdir(exist_ok=True)
    path = directory / f"proxies_{name}.txt"
    path.write_text("\n".join(proxies) + "\n", encoding="utf-8")
    return path


def subscription(**overrides):
    return {
        "id": "existing",
        "name": "nodes-dedicated",
        "source_type": "local",
        "content": PROXY_OLD + "\n",
        "last_error": "",
        "node_count": 1,
        **overrides,
    }


def test_first_sync_creates_local_subscription_refreshes_and_reads_result(resin_server, tmp_path):
    config, state = resin_server
    export(tmp_path, "first", PROXY_A)

    assert resin.sync(config, root=tmp_path) == 1

    row, = state["subscriptions"]
    assert row["name"] == "nodes-dedicated"
    assert row["source_type"] == "local"
    assert row["content"] == PROXY_A + "\n"
    assert [(method, path) for method, path, *_ in state["requests"]] == [
        ("GET", "/api/v1/subscriptions"),
        ("POST", "/api/v1/subscriptions"),
        ("POST", "/api/v1/subscriptions/created-1/actions/refresh"),
        ("GET", "/api/v1/subscriptions/created-1"),
    ]
    assert all(auth == "Bearer test-admin" for *_, auth in state["requests"])


def test_existing_subscription_merges_all_exports_and_remains_idempotent(resin_server, tmp_path):
    config, state = resin_server
    state["subscriptions"] = [subscription()]
    export(tmp_path, "account_a", PROXY_A, PROXY_A)
    export(tmp_path, "account_b", PROXY_B, PROXY_A, PROXY_OLD)

    assert resin.sync(config, root=tmp_path) == 3
    assert resin.sync(config, root=tmp_path) == 3

    assert len(state["subscriptions"]) == 1
    assert state["create_count"] == 0
    assert state["subscriptions"][0]["content"].splitlines() == [PROXY_OLD, PROXY_A, PROXY_B]
    updates = [payload for method, _, _, payload, _ in state["requests"] if method == "PATCH"]
    assert updates == [{"content": "\n".join([PROXY_OLD, PROXY_A, PROXY_B]) + "\n"}] * 2


def test_exact_name_is_found_on_later_page_without_modifying_similar_names(resin_server, tmp_path):
    config, state = resin_server
    similar = [subscription(id=f"other-{i}", name=f"nodes-dedicated-{i}") for i in range(101)]
    state["subscriptions"] = similar + [subscription()]
    export(tmp_path, "account", PROXY_A)

    assert resin.sync(config, root=tmp_path) == 2

    queries = [query for method, path, query, *_ in state["requests"]
               if method == "GET" and path == "/api/v1/subscriptions"]
    assert [query["offset"] for query in queries] == [["0"], ["100"]]
    assert all(query["keyword"] == ["nodes-dedicated"] for query in queries)
    assert all(row["content"] == PROXY_OLD + "\n" for row in similar)
    assert state["create_count"] == 0
    assert state["subscriptions"][-1]["content"] == PROXY_OLD + "\n" + PROXY_A + "\n"


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        ([subscription(), subscription(id="duplicate")], "同名"),
        ([subscription(source_type="remote")], "local"),
        ([subscription(content="ss://an-existing-node\n")], "HTTP"),
    ],
)
def test_unsafe_existing_subscription_is_never_written(resin_server, tmp_path, rows, error):
    config, state = resin_server
    state["subscriptions"] = rows
    original = json.loads(json.dumps(rows))
    path = export(tmp_path, "account", PROXY_A)

    with pytest.raises(RuntimeError, match=error):
        resin.sync(config, root=tmp_path)

    assert state["subscriptions"] == original
    assert all(method == "GET" for method, *_ in state["requests"])
    assert path.read_text() == PROXY_A + "\n"


@pytest.mark.parametrize("failure", ["authorization", "refresh"])
def test_remote_failure_is_diagnostic_and_preserves_local_export(resin_server, tmp_path, failure):
    config, state = resin_server
    path = export(tmp_path, "account", PROXY_A)
    if failure == "authorization":
        state["unauthorized"] = True
        expected = r"GET /subscriptions HTTP 401.*invalid admin token"
    else:
        state["refresh_error"] = "parse failed: invalid node text"
        expected = "parse failed: invalid node text"

    with pytest.raises(RuntimeError, match=expected) as caught:
        resin.sync(config, root=tmp_path)

    assert "--sync-resin" in str(caught.value)
    assert "本地节点已保留" in str(caught.value)
    assert path.read_text() == PROXY_A + "\n"


def test_retry_after_lost_create_response_finds_created_subscription(resin_server, tmp_path):
    config, state = resin_server
    state["drop_create_response"] = True
    path = export(tmp_path, "account", PROXY_A)

    with pytest.raises(RuntimeError, match="POST /subscriptions 未收到响应"):
        resin.sync(config, root=tmp_path)
    assert state["create_count"] == 1
    assert path.read_text() == PROXY_A + "\n"

    assert resin.sync(config, root=tmp_path) == 1

    assert state["create_count"] == 1
    assert len(state["subscriptions"]) == 1
    assert state["subscriptions"][0]["content"] == PROXY_A + "\n"
    assert any(method == "PATCH" for method, *_ in state["requests"])


@pytest.mark.parametrize("skip_empty", [False, True])
def test_empty_exports_never_make_http_requests(resin_server, tmp_path, skip_empty):
    config, state = resin_server
    export(tmp_path, "empty", "", " ")

    if skip_empty:
        assert resin.sync(config, root=tmp_path, skip_empty=True) == 0
    else:
        with pytest.raises(ValueError, match="没有可同步"):
            resin.sync(config, root=tmp_path)

    assert state["requests"] == []
