"""Use real HTTP on localhost to verify Cloud Mail and ProxyScrape request contracts."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

import proxy_service
import proxyscrape_register as app


@pytest.fixture
def api_server():
    state = {
        "accounts": [],
        "verification_sent": False,
        "verified": False,
        "requests": [],
        "login_count": 0,
        "expired": False,
        "expire_mail_auth": False,
        "mail_token": None,
        "trial_claimed": False,
        "trial_claims": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def dispatch(self):
            path = self.path.split("?")[0]
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            state["requests"].append((self.command, path, body))
            result = None
            status = 200
            if (
                path == "/mail/api/email/list"
                and state["verification_sent"]
                and state["expire_mail_auth"]
                and not state["expired"]
            ):
                state["expired"] = True
                state["mail_token"] = "revoked"
                self.respond({"code": 401, "message": "auth expired", "data": None})
                return
            if path == "/mail/api/login":
                assert json.loads(body) == {"email": "owner@example.org", "password": "secret"}
                state["login_count"] += 1
                state["mail_token"] = f"mail-session-{state['login_count']}"
                result = {"token": state["mail_token"]}
            elif path.startswith("/mail/api/"):
                assert self.headers["Authorization"] == state["mail_token"]
                if path.endswith("/setting/websiteConfig"):
                    result = {"domainList": ["@example.org"], "minEmailPrefix": 24}
                elif path.endswith("/account/list"):
                    result = state["accounts"]
                elif path.endswith("/account/add"):
                    email = json.loads(body)["email"]
                    result = {"accountId": 5, "email": email, "sort": 0}
                    state["accounts"].append(result)
                elif path.endswith("/email/list"):
                    rows = []
                    if state["verification_sent"]:
                        rows.append(
                            {
                                "emailId": 8,
                                "sendEmail": "no-reply@proxyscrape.com",
                                "toEmail": state["accounts"][0]["email"],
                                "subject": "Verify your email",
                                "content": "<b>Your verification code: aB3dE6gH9j</b>",
                            }
                        )
                    result = {"list": rows}
                result = {"code": 200, "data": result}
            elif path == "/register":
                assert b"cf_turnstile_token=local-token" in body
                result = {
                    "access_token": "local-access",
                    "userData": {"associatedSubaccounts": []},
                }
            else:
                assert self.headers["Authorization"] == "Bearer local-access"
                if path == "/resend":
                    state["verification_sent"] = True
                    result = {"success": True}
                elif path == "/verify":
                    assert "multipart/form-data" in self.headers["Content-Type"]
                    assert b'name="verificationCode"' in body
                    assert b"aB3dE6gH9j" in body
                    state["verified"] = True
                    result = {"success": True}
                elif path == "/me":
                    result = {"EmailVerified": state["verified"]}
                elif path.endswith("/premium/trial-eligibility"):
                    result = {"success": True, "claimed": state["trial_claimed"]}
                elif path.endswith("/premium/claim-trial"):
                    assert self.command == "POST"
                    assert state["trial_claimed"] is False
                    state["trial_claimed"] = True
                    state["trial_claims"] += 1
                    result = {"success": True, "account_id": "trial-42"}
                elif path.endswith("/account/subaccounts"):
                    result = {
                        "success": True,
                        "data": {
                            "subaccounts": [
                                {"AccountID": "trial-42", "AccountType": "premium"},
                            ]
                            if state["trial_claimed"]
                            else []
                        },
                    }
                elif path.endswith("/services/overview"):
                    result = {
                        "status": "valid",
                        "data": {
                            "is_trial": True,
                            "proxy_credentials_enabled": True,
                            "services": {
                                "datacenter_shared": {
                                    "proxy_username": "user",
                                    "proxy_password": "pass",
                                }
                            },
                        },
                    }
                elif path.endswith("/proxy-list"):
                    query = parse_qs(urlsplit(self.path).query)
                    assert query["format"] == ["json"]
                    assert query["type"] == ["displayproxies"]
                    assert query["protocol"] == ["http"]
                    result = {
                        "data": [
                            ["127.0.0.1:8000", "HTTP", "Online", "us"],
                            ["127.0.0.2:8001", "HTTP", "Online", "us"],
                        ],
                        "recordsFiltered": 2,
                    }
                else:
                    status = 404
                    result = {"error": "unknown endpoint"}
            if path == "/mail/api/login":
                result = {"code": 200, "data": result}
            self.respond(result, status)

        def respond(self, result, status=200):
            payload = result.encode() if isinstance(result, str) else json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("expire_mail_auth", [False, True])
def test_one_round_creates_mailbox_verifies_and_persists_exports(
    api_server,
    monkeypatch,
    tmp_path,
    expire_mail_auth,
):
    base, state = api_server
    state["expire_mail_auth"] = expire_mail_auth
    config = {
        "cloud_mail_url": base + "/mail",
        "cloud_mail_email": "owner@example.org",
        "cloud_mail_password": "secret",
        "browser_path": "",
        "turnstile_extension_path": "",
    }
    monkeypatch.setattr(app, "load_config", lambda _: config)
    monkeypatch.setattr(app, "solve_turnstile", lambda **kwargs: "local-token")
    monkeypatch.setattr(app, "_ACCOUNT_DIR", str(tmp_path / "account"))
    monkeypatch.setattr(app, "_NODE_DIR", str(tmp_path / "node"))
    monkeypatch.setattr(proxy_service, "BASE_URL", base)
    for name, path in [
        ("PS_REGISTER", "/register"),
        ("PS_RESEND", "/resend"),
        ("PS_VERIFY_EMAIL", "/verify"),
        ("PS_ME", "/me"),
    ]:
        monkeypatch.setattr(app, name, base + path)
    assert app.main(["--count", "1", "--threads", "1", "--attempts", "1"]) == 0
    records = list((tmp_path / "account").glob("*.jsonl"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["verified"] is True
    assert record["proxy_count"] == 2
    assert record["email"] == state["accounts"][0]["email"]
    exports = list((tmp_path / "node").glob("*.txt"))
    assert len(exports) == 1
    assert exports[0].read_text().splitlines() == [
        "http://user:pass@127.0.0.1:8000",
        "http://user:pass@127.0.0.2:8001",
    ]
    assert sum(path == "/mail/api/account/add" for _, path, _ in state["requests"]) == 1

    assert state["login_count"] == (2 if expire_mail_auth else 1)
    assert sum(path == "/register" for _, path, _ in state["requests"]) == 1
    assert sum(path == "/verify" for _, path, _ in state["requests"]) == 1
    assert len(state["accounts"]) == 1

    assert record["proxy_account_id"] == "trial-42"
    assert state["trial_claims"] == 1
    assert app.main(["--resume", record["email"]]) == 0
    assert state["trial_claims"] == 1
    assert sum(path == "/register" for _, path, _ in state["requests"]) == 1
    assert sum(path == "/verify" for _, path, _ in state["requests"]) == 1
    assert sum(path == "/mail/api/account/add" for _, path, _ in state["requests"]) == 1
    assert len(list((tmp_path / "node").glob("*.txt"))) == 2
