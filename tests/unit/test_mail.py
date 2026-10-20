import time

import pytest
import requests

from nodes.mail import CloudMail, extract_code


def message(**changes):
    return {
        "emailId": 11,
        "toEmail": "me@example.org",
        "sendEmail": "ProxyScrape <noreply@proxyscrape.com>",
        "subject": "Verify your email",
        "text": "Your verification code is 012345.",
        "content": "",
        **changes,
    }


def test_extracts_code_with_leading_zero():
    assert extract_code(message()) == "012345"


def test_extracts_html_without_treating_css_colors_as_codes():
    mail = message(text="", content="<style>.x {color:#123456}</style><b>654321</b>")
    assert extract_code(mail) == "654321"


@pytest.mark.parametrize("code", ["aB3dE6gH9j", "ABCDEFGHIJ", "0123456789"])
def test_extracts_ten_character_verification_code_from_html_preserving_case(code):
    mail = message(
        subject="ProxyScrape - Email Verification",
        text="Please open the HTML version of this email.",
        content=(
            "<style>.banner {color:#123456}</style>"
            f"<p>Here is your email verification code: <strong>{code}</strong></p>"
            '<a href="https://example.org/unsubscribe/999999">Unsubscribe From This List</a>'
        ),
    )
    assert extract_code(mail) == code


@pytest.mark.parametrize(
    "text",
    [
        "Your verification code expires in five minutes.",
        "Verification code: aB3dE6gH9jX",
        "An unrelated identifier is aB3dE6gH9j.",
    ],
)
def test_does_not_guess_or_truncate_an_alphanumeric_code(text):
    assert extract_code(message(text=text)) is None


def test_ambiguous_numbers_are_not_used_as_a_code():
    assert extract_code(message(text="Contact 12345678 or 87654321")) is None


class MailSession:
    def __init__(self, data, code=200, login_code=200, accounts=None):
        self.data = data
        self.code = code
        self.login_code = login_code
        self.requests = []
        self.accounts = accounts or [{"accountId": 7, "email": "me@example.org", "sort": 0}]

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.response(url, {"token": "login-token"}, self.login_code)

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        data = self.accounts if url.endswith("/account/list") else self.data
        return self.response(url, data, self.code)

    @staticmethod
    def response(url, data, code):
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = (
            __import__("json").dumps({"code": code, "message": "mail error", "data": data}).encode()
        )
        return response


def test_uses_cloud_mail_v3_password_login_and_scoped_mailbox():
    session = MailSession({"list": [message()]})
    mail = CloudMail("https://mail.example.org/", "me@example.org", "secret", session=session)
    assert mail.list_messages("me@example.org") == [message()]
    login_url, login_request = session.requests[0]
    assert login_url == "https://mail.example.org/api/login"
    assert login_request["json"] == {"email": "me@example.org", "password": "secret"}
    url, request = session.requests[-1]
    assert url == "https://mail.example.org/api/email/list"
    assert request["headers"]["Authorization"] == "login-token"
    assert request["params"] == {
        "accountId": 7,
        "allReceive": 0,
        "emailId": 0,
        "timeSort": 0,
        "size": 50,
        "type": 0,
    }
    mail.list_messages("me@example.org")
    assert sum(url.endswith("/login") for url, _ in session.requests) == 1


def test_http_200_with_cloud_mail_auth_error_is_reported():
    session = MailSession(None, login_code=401)
    mail = CloudMail("https://mail.example.org", "me@example.org", "secret", session=session)
    with pytest.raises(RuntimeError, match="401.*mail error"):
        mail.list_messages("me@example.org")
    assert len(session.requests) == 1


def test_poll_ignores_old_other_recipient_and_other_sender_messages():
    rows = [
        message(emailId=20, toEmail="other@example.org"),
        message(emailId=19, sendEmail="noreply@proxyscrape.com.attacker.org"),
        message(emailId=10),
        message(emailId=18, text="Verification code: 654321"),
    ]
    mail = CloudMail(
        "https://mail.example.org",
        "me@example.org",
        "secret",
        session=MailSession({"list": rows}),
    )
    assert mail.wait_for_code("me@example.org", after_id=10, timeout=1) == "654321"


def test_mail_timeout_does_not_accept_previous_code():
    mail = CloudMail(
        "https://mail.example.org",
        "me@example.org",
        "secret",
        session=MailSession({"list": [message()]}),
    )
    with pytest.raises(TimeoutError, match="验证码"):
        mail.wait_for_code("me@example.org", after_id=11, timeout=0.01, poll_interval=0.001)


@pytest.mark.parametrize(
    "rows,reason,counts",
    [
        ([], "未找到新邮件", "返回 0 封，新邮件 0 封，匹配 0 封"),
        ([message(emailId=10)], "未找到新邮件", "返回 1 封，新邮件 0 封，匹配 0 封"),
        (
            [
                message(toEmail="other@example.org"),
                message(emailId=12, sendEmail="other@example.org"),
            ],
            "新邮件未匹配目标收件地址及 ProxyScrape 发件域名",
            "返回 2 封，新邮件 2 封，匹配 0 封",
        ),
        (
            [message(text="private-body", content="")],
            "匹配邮件中未解析到验证码",
            "返回 1 封，新邮件 1 封，匹配 1 封",
        ),
    ],
)
def test_mail_timeout_explains_last_query_without_message_content(rows, reason, counts):
    mail = CloudMail(
        "https://mail.example.org",
        "me@example.org",
        "secret",
        session=MailSession({"list": rows}),
    )
    with pytest.raises(TimeoutError) as error:
        mail.wait_for_code("me@example.org", after_id=10, timeout=0)
    detail = str(error.value)
    assert reason in detail
    assert counts in detail
    assert "基线编号 10" in detail
    assert "private-body" not in detail
    assert "012345" not in detail


def test_rejects_incompatible_mail_response_instead_of_waiting_silently():
    mail = CloudMail(
        "https://mail.example.org",
        "me@example.org",
        "secret",
        session=MailSession({"rows": []}),
    )
    with pytest.raises(RuntimeError, match="列表"):
        mail.list_messages("me@example.org")


def test_missing_mailbox_fails_before_registration():
    mail = CloudMail(
        "https://mail.example.org",
        "me@example.org",
        "secret",
        session=MailSession({"list": []}),
    )
    with pytest.raises(ValueError, match="不存在"):
        mail.list_messages("missing@example.org")


class MailboxSession(MailSession):
    def post(self, url, **kwargs):
        if url.endswith("/login"):
            return super().post(url, **kwargs)
        self.requests.append((url, kwargs))
        assert url.endswith("/account/add")
        assert kwargs["headers"]["Authorization"] == "login-token"
        row = {"accountId": 8, "email": kwargs["json"]["email"], "sort": 0}
        self.accounts.append(row)
        return self.response(url, row, self.code)

    def get(self, url, **kwargs):
        if not url.endswith("/setting/websiteConfig"):
            return super().get(url, **kwargs)
        self.requests.append((url, kwargs))
        assert kwargs["headers"]["Authorization"] == "login-token"
        return self.response(url, {"domainList": ["@example.org"], "minEmailPrefix": 30}, 200)


def test_random_address_is_created_once_and_receives_in_its_own_mailbox():
    session = MailboxSession({"list": []})
    mail = CloudMail("https://mail.example.org", "me@example.org", "secret", session=session)
    email = mail.new_address()
    prefix, domain = email.split("@")
    assert domain == "example.org"
    assert len(prefix) == 30
    assert all(char in "0123456789abcdef" for char in prefix)
    mail.ensure_mailbox(email)
    mail.ensure_mailbox(email)
    assert mail.list_messages(email) == []
    assert sum(url.endswith("/account/add") for url, _ in session.requests) == 1
    assert session.requests[-1][1]["params"]["accountId"] == 8


def test_mailbox_creation_error_is_reported():
    session = MailboxSession({"list": []}, code=403)
    mail = CloudMail("https://mail.example.org", "me@example.org", "secret", session=session)
    # 列表读取成功，只有创建失败。
    session.get = lambda url, **kwargs: session.response(url, [], 200)
    with pytest.raises(RuntimeError, match="403.*mail error"):
        mail.ensure_mailbox("new@example.org")


def test_mailbox_created_before_a_lost_response_is_found_on_retry():
    session = MailboxSession({"list": []})
    original_post = session.post

    def lose_response(url, **kwargs):
        response = original_post(url, **kwargs)
        if url.endswith("/account/add"):
            raise requests.Timeout("response lost")
        return response

    session.post = lose_response
    mail = CloudMail("https://mail.example.org", "me@example.org", "secret", session=session)
    with pytest.raises(requests.Timeout):
        mail.ensure_mailbox("new@example.org")
    session.post = original_post
    resumed = CloudMail("https://mail.example.org", "me@example.org", "secret", session=session)
    resumed.ensure_mailbox("new@example.org")
    assert sum(url.endswith("/account/add") for url, _ in session.requests) == 1


def test_existing_auth_is_reused_between_requests():
    session = MailSession({"list": [message()]})
    mail = CloudMail(
        "https://mail.example.org",
        "me@example.org",
        "secret",
        session=session,
    )
    mail.token = "round-token"
    assert mail.list_messages("me@example.org") == [message()]
    assert not any(url.endswith("/login") for url, _ in session.requests)
    assert all(
        request["headers"]["Authorization"] == "round-token" for _, request in session.requests
    )


class ExpiredSession(MailSession):
    def __init__(self, *, persistent=False, failure_code=401, http_status=200):
        super().__init__({"list": [message()]})
        self.persistent = persistent
        self.failure_code = failure_code
        self.http_status = http_status
        self.logins = 0

    def post(self, url, **kwargs):
        if url.endswith("/login"):
            self.requests.append((url, kwargs))
            self.logins += 1
            time.sleep(0.01)  # Model the login HTTP call while other workers are active.
            return self.response(url, {"token": f"fresh-{self.logins}"}, 200)
        return self.protected(url, kwargs)

    def get(self, url, **kwargs):
        return self.protected(url, kwargs)

    def protected(self, url, kwargs):
        self.requests.append((url, kwargs))
        if self.persistent or kwargs["headers"].get("Authorization") != f"fresh-{self.logins}":
            response = self.response(url, None, self.failure_code)
            response.status_code = self.http_status
            return response
        if url.endswith("/account/add"):
            return self.response(url, {"accountId": 8}, 200)
        return self.response(url, self.data, 200)


def expired_mail(session):
    mail = CloudMail("https://mail.example.org", "me@example.org", "secret", session=session)
    mail.token = "expired-token"
    return mail


@pytest.mark.parametrize("http_status", [200, 401])
def test_expired_auth_logs_in_once_then_repeats_the_same_request(http_status, caplog):
    session = ExpiredSession(http_status=http_status)
    mail = expired_mail(session)
    data = mail._request("GET", "/email/list", params={"accountId": 7})
    assert data == {"list": [message()]}
    assert session.logins == 1
    reads = [kwargs for url, kwargs in session.requests if url.endswith("/email/list")]
    assert len(reads) == 2
    assert reads[0]["params"] == reads[1]["params"] == {"accountId": 7}
    assert reads[0]["headers"]["Authorization"] == "expired-token"
    assert reads[1]["headers"]["Authorization"] == "fresh-1"
    assert "GET /email/list" in caplog.text
    assert "expired-token" not in caplog.text
    assert "fresh-1" not in caplog.text


def test_second_auth_failure_is_reported_with_endpoint_without_another_login():
    session = ExpiredSession(persistent=True)
    mail = expired_mail(session)
    with pytest.raises(RuntimeError, match="GET /account/list.*401.*mail error"):
        mail._request("GET", "/account/list", params={"accountId": 0})
    assert session.logins == 1
    assert len(session.requests) == 3


def test_expired_auth_repeats_mailbox_creation_with_the_same_address():
    session = ExpiredSession()
    mail = expired_mail(session)
    mail._find_account = lambda email: None
    mail.ensure_mailbox("new@example.org")
    posts = [kwargs for url, kwargs in session.requests if url.endswith("/account/add")]
    assert len(posts) == 2
    assert [request["json"] for request in posts] == [{"email": "new@example.org"}] * 2
    assert mail.accounts["new@example.org"] == 8
    assert session.logins == 1


@pytest.mark.parametrize("code", [403, 500])
def test_non_auth_api_errors_are_not_retried(code):
    session = ExpiredSession(failure_code=code)
    mail = expired_mail(session)
    with pytest.raises(RuntimeError, match=f"POST /account/add.*{code}"):
        mail._request("POST", "/account/add", json={"email": "new@example.org"})
    assert session.logins == 0
    assert len(session.requests) == 1


def test_network_timeout_does_not_repeat_a_mailbox_creation():
    session = MailSession({})
    calls = []

    def timeout(url, **kwargs):
        calls.append(url)
        raise requests.Timeout("response lost")

    session.post = timeout
    mail = expired_mail(session)
    with pytest.raises(requests.Timeout, match="response lost"):
        mail._request("POST", "/account/add", json={"email": "new@example.org"})
    assert len(calls) == 1


def test_concurrent_mail_requests_share_one_auth_renewal():
    from concurrent.futures import ThreadPoolExecutor

    session = ExpiredSession()
    mail = expired_mail(session)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: mail._request("GET", "/email/list"), range(8)))
    assert results == [{"list": [message()]}] * 8
    assert session.logins == 1
    assert mail.token == "fresh-1"


def test_failed_auth_renewal_does_not_repeat_login_or_the_original_request():
    session = ExpiredSession()
    original_post = session.post

    def fail_login(url, **kwargs):
        if url.endswith("/login"):
            session.requests.append((url, kwargs))
            return session.response(url, None, 401)
        return original_post(url, **kwargs)

    session.post = fail_login
    mail = expired_mail(session)
    with pytest.raises(RuntimeError, match="POST /login.*401"):
        mail._request("GET", "/email/list")
    assert len(session.requests) == 2


@pytest.mark.parametrize("http_status", [403, 500])
def test_non_auth_http_errors_are_not_retried(http_status):
    session = ExpiredSession(http_status=http_status)
    mail = expired_mail(session)
    with pytest.raises(requests.HTTPError, match=str(http_status)):
        mail._request("POST", "/account/add", json={"email": "new@example.org"})
    assert session.logins == 0
    assert len(session.requests) == 1
