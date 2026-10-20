import pytest
import requests

from nodes import resin


@pytest.mark.parametrize("token", ["private-admin-token", "invalid\nprivate-admin-token"])
def test_sync_error_keeps_context_but_does_not_print_admin_token(monkeypatch, tmp_path, token):
    directory = tmp_path / "node"
    directory.mkdir()
    path = directory / "proxies_test.txt"
    path.write_text("http://user:password@127.0.0.1:8000\n")

    def invalid_header(*args, **kwargs):
        value = f"Bearer {token}"
        raise requests.exceptions.InvalidHeader(f"Invalid Authorization header value {value!r}")

    monkeypatch.setattr(requests.Session, "request", invalid_header)
    config = {"resin_url": "https://resin.example.org", "resin_admin_token": token}
    with pytest.raises(RuntimeError) as caught:
        resin.sync(config, root=tmp_path)
    detail = str(caught.value)
    assert token not in detail
    assert repr(token) not in detail
    assert repr(token)[1:-1] not in detail
    assert "GET /subscriptions" in detail
    assert "Invalid Authorization header" in detail
    assert "--sync-resin" in detail
    assert path.exists()


def test_real_requests_invalid_header_does_not_leak_escaped_token(monkeypatch, tmp_path):
    directory = tmp_path / "node"
    directory.mkdir()
    (directory / "proxies_test.txt").write_text("http://user:password@127.0.0.1:8000\n")
    token = "invalid\nprivate-admin-token"

    def no_network(*args, **kwargs):
        pytest.fail("An invalid header must fail before network I/O")

    monkeypatch.setattr(requests.Session, "send", no_network)
    config = {"resin_url": "http://127.0.0.1:1", "resin_admin_token": token}
    with pytest.raises(RuntimeError) as caught:
        resin.sync(config, root=tmp_path)
    detail = str(caught.value)
    assert token not in detail
    assert repr(token)[1:-1] not in detail
    assert "GET /subscriptions" in detail
    assert "--sync-resin" in detail
