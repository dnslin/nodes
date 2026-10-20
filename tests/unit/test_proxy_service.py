import json
from urllib.parse import urlsplit

import pytest
import requests

from nodes.api import fetch_trial_proxies

PREFIX = "/v2/v4/account"
ELIGIBILITY = f"{PREFIX}/premium/trial-eligibility"
CLAIM = f"{PREFIX}/premium/claim-trial"
SUBACCOUNTS = f"{PREFIX}/subaccounts"
OVERVIEW = f"{PREFIX}/trial-id/services/overview"
PROXIES = f"{PREFIX}/trial-id/datacenter_shared/proxy-list"
ROW = ["192.0.2.1:3129", "HTTP", "Online", "us"]


def overview(**changes):
    data = {
        "is_trial": True,
        "proxy_credentials_enabled": True,
        "services": {
            "datacenter_shared": {
                "proxy_username": "trial-user",
                "proxy_password": "trial-pass",
            }
        },
    }
    data.update(changes)
    return {"success": True, "status": "valid", "data": data}


class Session:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def request(self, method, url, **kwargs):
        path = urlsplit(url).path
        self.calls.append((method, path, kwargs))
        expected_method, expected_path, body, status = self.replies.pop(0)
        assert (method, path) == (expected_method, expected_path)
        assert kwargs["headers"]["Authorization"] == "Bearer saved-token"
        if isinstance(body, Exception):
            raise body
        response = requests.Response()
        response.status_code = status
        response.url = url
        response._content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return response


def reply(method, path, body, status=200):
    return method, path, body, status


def unclaimed(*after_claim):
    return Session(
        reply("GET", ELIGIBILITY, {"success": True, "claimed": False}),
        reply("POST", CLAIM, {"success": True, "account_id": "trial-id"}),
        *after_claim,
    )


def test_claims_once_without_assuming_registration_created_a_subaccount():
    session = unclaimed(
        reply("GET", OVERVIEW, overview()),
        reply("GET", PROXIES, {"data": [ROW], "recordsFiltered": 1}),
    )
    assert fetch_trial_proxies(session, "saved-token") == (
        "trial-id",
        "trial-user",
        "trial-pass",
        ["192.0.2.1:3129"],
    )
    assert [call[:2] for call in session.calls] == [
        ("GET", ELIGIBILITY),
        ("POST", CLAIM),
        ("GET", OVERVIEW),
        ("GET", PROXIES),
    ]
    assert session.calls[-1][2]["params"] == {
        "format": "json",
        "type": "displayproxies",
        "protocol": "http",
        "start": 0,
        "length": 100,
    }


def test_existing_trial_is_selected_instead_of_first_paid_account_and_overview_is_reused():
    paid_path = f"{PREFIX}/paid-id/services/overview"
    session = Session(
        reply("GET", ELIGIBILITY, {"claimed": True}),
        reply(
            "GET",
            SUBACCOUNTS,
            {
                "data": {
                    "subaccounts": [
                        {"AccountID": "paid-id", "AccountType": "premium"},
                        {"AccountID": "ignored", "AccountType": "residential"},
                        {"AccountID": "trial-id", "AccountType": "datacenter_shared"},
                    ],
                    "total": 3,
                }
            },
        ),
        reply("GET", paid_path, overview(is_trial=False)),
        reply("GET", OVERVIEW, overview()),
        reply("GET", PROXIES, {"data": [ROW], "recordsFiltered": 1}),
    )
    assert fetch_trial_proxies(session, "saved-token")[0] == "trial-id"
    assert all(method == "GET" for method, _, _ in session.calls)
    assert sum(path == OVERVIEW for _, path, _ in session.calls) == 1
    assert session.replies == []


def test_json_proxy_rows_are_paginated_and_only_endpoints_are_returned():
    other = ["192.0.2.2:8080", "HTTP", "Online", "de"]
    session = unclaimed(
        reply("GET", OVERVIEW, overview()),
        reply("GET", PROXIES, {"data": [ROW], "recordsFiltered": 2}),
        reply("GET", PROXIES, {"data": [other], "recordsFiltered": 2}),
    )
    assert fetch_trial_proxies(session, "saved-token")[3] == [ROW[0], other[0]]
    assert [kwargs["params"]["start"] for _, path, kwargs in session.calls if path == PROXIES] == [
        0,
        1,
    ]


@pytest.mark.parametrize(
    "failure,status,detail",
    [
        ({"success": False, "error": "Trial rejected"}, 200, "Trial rejected"),
        ({"message": "Forbidden"}, 403, "Forbidden"),
        ({"info": "Service unavailable"}, 503, "Service unavailable"),
        (requests.ConnectionError("response lost"), None, "response lost"),
        ({"success": True}, 200, "account_id"),
    ],
)
def test_claim_failure_or_lost_response_never_retries_post(failure, status, detail):
    session = Session(
        reply("GET", ELIGIBILITY, {"claimed": False}),
        reply("POST", CLAIM, failure, status),
    )
    with pytest.raises(RuntimeError) as error:
        fetch_trial_proxies(session, "saved-token")
    assert f"POST {CLAIM}" in str(error.value)
    assert "HTTP" in str(error.value)
    assert detail in str(error.value)
    assert sum(method == "POST" for method, _, _ in session.calls) == 1


@pytest.mark.parametrize("body", [{}, {"claimed": "false"}, {"claimed": 0}, [], b"not json"])
def test_invalid_eligibility_fails_before_claiming(body):
    session = Session(reply("GET", ELIGIBILITY, body))
    with pytest.raises(RuntimeError, match=f"GET {ELIGIBILITY} HTTP 200"):
        fetch_trial_proxies(session, "saved-token")
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "change,detail",
    [
        ({"is_trial": False}, "试用"),
        ({"proxy_credentials_enabled": False}, "认证"),
        ({"services": {}}, "认证"),
        (
            {"services": {"datacenter_shared": {"proxy_username": "u", "proxy_password": ""}}},
            "认证",
        ),
    ],
)
def test_non_trial_or_missing_credentials_cannot_export(change, detail):
    session = unclaimed(reply("GET", OVERVIEW, overview(**change)))
    with pytest.raises(RuntimeError) as error:
        fetch_trial_proxies(session, "saved-token")
    assert f"GET {OVERVIEW} HTTP 200" in str(error.value)
    assert detail in str(error.value)
    assert len(session.calls) == 3


@pytest.mark.parametrize("status", ["expired", "paused", "suspended", None])
def test_unavailable_overview_status_cannot_export(status):
    body = overview()
    body["status"] = status
    session = unclaimed(reply("GET", OVERVIEW, body))
    with pytest.raises(RuntimeError, match="当前不可用"):
        fetch_trial_proxies(session, "saved-token")


@pytest.mark.parametrize(
    "body,detail",
    [
        ({"data": [], "recordsFiltered": 1}, "分页"),
        ({"data": [], "recordsFiltered": 0}, "为空"),
        ({"data": {"error": "not rows"}, "recordsFiltered": 1}, "data"),
        ({"data": [ROW]}, "recordsFiltered"),
        ({"data": ["192.0.2.1:3129"], "recordsFiltered": 1}, "节点格式"),
        ({"data": [["192.0.2.1:3129"]], "recordsFiltered": 1}, "节点格式"),
        ({"data": [['{"error":true}', "HTTP", "Online", "us"]], "recordsFiltered": 1}, "端口"),
        ({"success": False, "info": "Not ready"}, "Not ready"),
    ],
)
def test_invalid_proxy_response_is_not_interpreted_as_node_text(body, detail):
    session = unclaimed(
        reply("GET", OVERVIEW, overview()),
        reply("GET", PROXIES, body),
    )
    with pytest.raises(RuntimeError) as error:
        fetch_trial_proxies(session, "saved-token")
    assert f"GET {PROXIES} HTTP 200" in str(error.value)
    assert detail in str(error.value)


@pytest.mark.parametrize("count", [0, 2])
def test_claimed_account_requires_exactly_one_trial_and_never_claims_again(count):
    accounts = [{"AccountID": f"trial-{i}", "AccountType": "premium"} for i in range(count)]
    session = Session(
        reply("GET", ELIGIBILITY, {"claimed": True}),
        reply("GET", SUBACCOUNTS, {"data": {"subaccounts": accounts}}),
        *(
            reply("GET", f"{PREFIX}/{row['AccountID']}/services/overview", overview())
            for row in accounts
        ),
    )
    with pytest.raises(RuntimeError, match=f"找到 {count} 个"):
        fetch_trial_proxies(session, "saved-token")
    assert all(method == "GET" for method, _, _ in session.calls)


def test_lost_claim_response_can_resume_without_a_second_claim():
    session = Session(
        reply("GET", ELIGIBILITY, {"claimed": False}),
        reply("POST", CLAIM, requests.ConnectionError("claim response lost")),
        reply("GET", ELIGIBILITY, {"claimed": True}),
        reply(
            "GET",
            SUBACCOUNTS,
            {
                "data": {
                    "subaccounts": [
                        {"AccountID": "trial-id", "AccountType": "premium"},
                    ]
                }
            },
        ),
        reply("GET", OVERVIEW, overview()),
        reply("GET", PROXIES, {"data": [ROW], "recordsFiltered": 1}),
    )
    with pytest.raises(RuntimeError, match="claim response lost"):
        fetch_trial_proxies(session, "saved-token")
    assert fetch_trial_proxies(session, "saved-token")[0] == "trial-id"
    assert sum(method == "POST" for method, _, _ in session.calls) == 1


def test_http_error_keeps_all_server_diagnostic_fields():
    session = Session(
        reply(
            "GET",
            ELIGIBILITY,
            {
                "error": "unavailable",
                "message": "trial service failed",
                "info": "try later",
            },
            503,
        )
    )
    with pytest.raises(RuntimeError) as error:
        fetch_trial_proxies(session, "saved-token")
    text = str(error.value)
    assert f"GET {ELIGIBILITY} HTTP 503" in text
    assert "unavailable" in text
    assert "trial service failed" in text
    assert "try later" in text
