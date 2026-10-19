"""Nodes 的 Cloud Mail 3.0.0 版本，支持交互式与命令行运行。"""

import argparse
import json
import os
import random
import string
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import requests

from cloud_mail import CloudMail
from nodes_config import load_config
from proxy_service import fetch_trial_proxies

_BASE = os.path.dirname(os.path.abspath(__file__))


# ProxyScrape dashboard
PS_BASE = "https://dashboard.proxyscrape.com"
PS_REGISTER = f"{PS_BASE}/v2/v4/account/auth/register"
PS_LOGIN = f"{PS_BASE}/v2/v4/account/auth/login"
PS_ME = f"{PS_BASE}/v2/v4/account/auth/me"
PS_VERIFY_EMAIL = f"{PS_BASE}/v2/v4/account/verify-email"
PS_RESEND = f"{PS_BASE}/v2/v4/account/reset-verification-code"
PS_SIGNUP_PAGE = f"{PS_BASE}/v2/sign-up"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)

# 输出目录：账号 → account/  代理节点 → node/
_ACCOUNT_DIR = os.path.join(_BASE, "account")
_NODE_DIR = os.path.join(_BASE, "node")

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": UA,
    "Origin": PS_BASE,
    "Referer": PS_SIGNUP_PAGE,
}


_print_lock = threading.Lock()
_file_lock = threading.Lock()
_tls = threading.local()


def log(msg):
    tag = getattr(_tls, "tag", "")
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}]{tag} {msg}", flush=True)


# ── 本地打码：浏览器只出 token ───────────────────────────
# 触发 widget 挂载：填占位表单（token 不绑定表单内容，随便填合法值即可）
_FILL_JS = r"""
function setVal(el,val){
  var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
  setter.call(el,val);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
}
var email=document.querySelector('input[type=email]');
var pwds=document.querySelectorAll('input[type=password]');
var chk=document.querySelector('input[type=checkbox]');
if(email) setVal(email,'warmup'+Date.now()+'@example.com');
if(pwds[0]) setVal(pwds[0],'Warmup123!9');
if(pwds[1]) setVal(pwds[1],'Warmup123!9');
if(chk&&!chk.checked) chk.click();
return 'filled';
"""

# 一次读全 widget 状态（供轮询检测用，不盲等）：页面/API/input/iframe/token
_STATE_JS = r"""
try{
  var inp=document.querySelector('input[name="cf-turnstile-response"]');
  var token=inp?String(inp.value||'').trim():'';
  if(!token && window.turnstile && typeof turnstile.getResponse==='function'){
    try{ token=String(turnstile.getResponse()||'').trim(); }catch(e){}
  }
  return JSON.stringify({
    ready: document.readyState==='complete',
    hasApi: !!(window.turnstile && typeof turnstile.render==='function'),
    hasInput: !!inp,
    tokenLen: token.length,
    token: token.length>=80 ? token : ''
  });
}catch(e){ return JSON.stringify({err:String(e)}); }
"""

_TURNSTILE_FRAME = 'css:iframe[src*="challenges.cloudflare.com"],iframe[src*="turnstile"]'


def _read_state(tab):
    """页面脚本读状态；浏览器库查找封闭 Shadow DOM 内的 iframe。"""
    state = json.loads(tab.run_js(_STATE_JS))
    if state.get("err"):
        raise RuntimeError(f"读取 Turnstile 页面状态失败: {state['err']}")
    state["hasIframe"] = bool(tab.ele(_TURNSTILE_FRAME, timeout=0))
    return state


def solve_turnstile(headless=False, timeout=120, config=None):
    """等待站点原生验证组件，不创建重复 widget，超时保留实际阶段。"""
    from DrissionPage import Chromium
    from DrissionPage.errors import ContextLostError, ElementLostError

    from browser_runtime import browser_options

    config = config or load_config(_BASE)
    opts = browser_options(
        headless,
        config["browser_path"],
        config["turnstile_extension_path"],
    )
    browser = Chromium(opts)
    tab = browser.latest_tab
    deadline = time.monotonic() + timeout
    stage = "等待页面及 Turnstile API"
    last_stage = None
    last_error = None
    state = {}
    filled = False
    try:
        log("浏览器打开 sign-up 页…")
        tab.get(PS_SIGNUP_PAGE)
        while time.monotonic() < deadline:
            try:
                state = _read_state(tab)
                if state.get("token"):
                    log(f"Turnstile 通过，token 长度={state['tokenLen']}")
                    return state["token"]
                if not (state.get("ready") and state.get("hasApi")):
                    stage = "等待页面及 Turnstile API"
                elif not filled:
                    tab.run_js(_FILL_JS)
                    filled = True
                    stage = "等待验证组件挂载"
                elif not state.get("hasInput"):
                    stage = "等待 cf-turnstile-response 挂载"
                elif not state.get("hasIframe"):
                    stage = "等待站点原生验证 iframe"
                else:
                    stage = "等待验证结果"
                    iframe = tab.ele(_TURNSTILE_FRAME, timeout=0)
                    if iframe:
                        body = iframe.ele("tag:body", timeout=0)
                        root = body.shadow_root if body else None
                        button = root.ele("tag:input", timeout=0) if root else None
                        if button:
                            button.click()
            except (ContextLostError, ElementLostError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log(f"验证页面更新，重新定位: {last_error}")
            if stage != last_stage:
                log(f"Turnstile 阶段: {stage}")
                last_stage = stage
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.5, remaining))
        detail = (
            f"Turnstile 超时：阶段={stage}；"
            f"hasInput={bool(state.get('hasInput'))}；"
            f"hasIframe={bool(state.get('hasIframe'))}；"
            f"tokenLength={state.get('tokenLen', 0)}"
        )
        if last_error:
            detail += f"；最后页面异常={last_error}"
        raise TimeoutError(detail)
    finally:
        try:
            browser.quit()
        except Exception as exc:
            log(f"[!] 关闭浏览器失败: {exc}")


# ── 注册（协议）─────────────────────────────────────────
def register(email, password, turnstile_token):
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.post(
        PS_REGISTER,
        data={
            "email": email,
            "password": password,
            "cf_turnstile_token": turnstile_token,
        },
        timeout=30,
    )
    log(f"注册响应 HTTP {r.status_code}")
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("注册未返回 access_token")
    log("注册成功，已取得访问凭据")
    return s, token, data.get("userData", {})


def resend_code(session, access_token):
    """触发发送/重发验证码（注册后不会自动发，必须调一次）。"""
    r = session.post(PS_RESEND, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    log(f"发送验证邮件 HTTP {r.status_code}")
    r.raise_for_status()
    return True


def verify_email(session, access_token, code):
    # 关键：字段名是 verificationCode（不是 code），且服务端要 multipart/form-data
    r = session.post(
        PS_VERIFY_EMAIL,
        headers={"Authorization": f"Bearer {access_token}"},
        files={"verificationCode": (None, code)},
        timeout=30,
    )
    log(f"验邮箱响应 HTTP {r.status_code}")
    r.raise_for_status()
    return True


def whoami(session, access_token):
    r = session.post(PS_ME, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def _format_proxy_url(user, pwd, ip):
    return f"http://{quote(user, safe='')}:{quote(pwd, safe='')}@{ip}"


def save_proxies(user, pwd, proxies, path):
    """追加写入本轮代理文件，格式 http://user:pass@ip:port。"""
    with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            for ip in proxies:
                f.write(f"{_format_proxy_url(user, pwd, ip)}\n")


# ── 单个账号注册（并发 worker）───────────────────────────
def save_account(rec, path):
    with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def complete_proxy_export(rec, session, node_file):
    current = whoami(session, rec["access_token"])
    rec["verified"] = current.get("EmailVerified") is True
    rec["userData"] = current
    if not rec["verified"]:
        raise RuntimeError("ProxyScrape 服务端尚未确认邮箱验证成功，未开通试用")
    log("正在查询当前账号的 Premium 试用状态并导出代理…")
    account_id, username, password, proxies = fetch_trial_proxies(session, rec["access_token"])
    save_proxies(username, password, proxies, node_file)
    rec.update(
        proxy_account_id=account_id,
        proxy_username=username,
        proxy_password=password,
        proxy_count=len(proxies),
    )
    rec.pop("error", None)
    log(f"已导出 {len(proxies)} 个代理，子账号 {account_id}")


def resume_account(email):
    matched = None
    for path in sorted(Path(_ACCOUNT_DIR).glob("accounts_*.jsonl"), reverse=True):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("email") == email:
                matched = path, row
                break
        if matched:
            break
    if matched is None:
        raise ValueError(f"在 {_ACCOUNT_DIR} 中没有找到已保存的账号 {email}")
    path, rec = matched
    if not rec.get("access_token"):
        raise ValueError(f"账号文件 {path} 中没有 {email} 的访问凭据")
    os.makedirs(_NODE_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000_000:09d}"
    node_file = os.path.join(_NODE_DIR, f"proxies_resume_{stamp}.txt")
    log(f"继续已保存的账号 {email}，账号文件 {path}")
    try:
        with requests.Session() as session:
            session.headers.update(HEADERS)
            complete_proxy_export(rec, session, node_file)
    except Exception as exc:
        rec.update(error=str(exc), proxy_count=0)
        save_account(rec, path)
        log(f"[!] 账号 {email} 导出失败: {exc}")
        return False
    save_account(rec, path)
    log(f"代理文件 → {node_file}")
    return True


def _register_once(
    headless,
    node_file,
    config,
    mail,
    *,
    mail_timeout=180,
    challenge_timeout=120,
):
    """建 Cloud Mail 附属邮箱，再执行 Nodes 的注册、验证和代理导出流程。"""
    email = mail.new_address()
    mail.ensure_mailbox(email)
    log(f"Cloud Mail 邮箱: {email}")
    after_id = max((row["emailId"] for row in mail.list_messages(email)), default=0)
    password = "Ps" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "!9"
    token = solve_turnstile(headless=headless, timeout=challenge_timeout, config=config)
    session, access_token, userdata = register(email, password, token)
    rec = {
        "email": email,
        "password": password,
        "access_token": access_token,
        "userData": userdata,
        "verified": False,
        "proxy_username": "",
        "proxy_password": "",
        "proxy_count": 0,
        "ts": int(time.time()),
    }
    try:
        resend_code(session, access_token)
        log("等待 Cloud Mail 新验证邮件…")
        code = mail.wait_for_code(email, after_id=after_id, timeout=mail_timeout)
        if not verify_email(session, access_token, code):
            raise RuntimeError("ProxyScrape 拒绝邮箱验证码")
        complete_proxy_export(rec, session, node_file)
    except Exception as exc:
        rec["error"] = str(exc)
        log(f"[!] 账号 {email} 后续处理失败: {exc}")
    finally:
        session.close()
    return rec


def register_one(idx, headless, acc_file, node_file, config, mail, max_attempts=3, **kwargs):
    """保留 Nodes 的账号级重试，每个已注册账号都保存，失败会写明原因。"""
    _tls.tag = f" #{idx}"
    last = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            log(f"—— 第 {attempt}/{max_attempts} 次尝试 ——")
        try:
            rec = _register_once(headless, node_file, config, mail, **kwargs)
        except Exception as exc:
            log(f"[x] 本次尝试失败: {exc}")
            continue
        save_account(rec, acc_file)
        last = rec
        if rec["proxy_count"] > 0:
            log(f"[✓] 完成 {rec['email']} · 代理 {rec['proxy_count']} 个")
            return rec
        if attempt < max_attempts:
            log("已保存未完成账号，按 Nodes 的重试方式使用新邮箱再次尝试")
    log(f"[x] #{idx} 未完成代理导出，已尝试 {max_attempts} 次")
    return last


# ── 启动引导 ────────────────────────────────────────────
def _ask(prompt, default):
    try:
        v = input(prompt).strip()
    except EOFError:
        v = ""
    return v or default


def guide():
    print("=" * 52)
    print("   ProxyScrape 批量注册机  ·  本地打码走协议")
    print("   浏览器只出 Turnstile token，注册/收信/验证全走 HTTP")
    print("   邮箱: Cloud Mail 3.0.0   账号→account/  代理→node/")
    print("=" * 52)
    try:
        count = int(_ask("① 注册数量        [默认 5，输 0 退出]: ", "5"))
    except ValueError:
        count = 5
    try:
        threads = int(_ask("② 并发线程        [默认 3]: ", "3"))
    except ValueError:
        threads = 3
    hl = _ask("③ 隐藏浏览器窗口   [Y/n]: ", "Y").lower()
    headless = not hl.startswith("n")
    threads = max(1, min(threads, count, 8))  # 并发上限 8，别把机器压垮
    print("-" * 52)
    print(f"  → 注册 {count} 个 · 并发 {threads} · {'隐藏窗口' if headless else '显示窗口'}")
    print("-" * 52)
    return count, threads, headless


def run_round(count, threads, headless, config, **kwargs):
    mail = CloudMail(
        config["cloud_mail_url"],
        config["cloud_mail_email"],
        config["cloud_mail_password"],
    )
    try:
        mail._login()
        # 每轮独立文件（时间戳命名），不追加旧文件
        os.makedirs(_ACCOUNT_DIR, exist_ok=True)
        os.makedirs(_NODE_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000_000:09d}"
        acc_file = os.path.join(_ACCOUNT_DIR, f"accounts_{ts}.jsonl")
        node_file = os.path.join(_NODE_DIR, f"proxies_{ts}.txt")
        t0 = time.time()
        ok = []
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futs = {
                ex.submit(
                    register_one,
                    i + 1,
                    headless,
                    acc_file,
                    node_file,
                    config,
                    mail,
                    **kwargs,
                ): i + 1
                for i in range(count)
            }
            for fu in as_completed(futs):
                try:
                    r = fu.result()
                except Exception as e:
                    r = None
                    with _print_lock:
                        print(f"[worker error] {e}", flush=True)
                if r and r.get("proxy_count", 0) > 0:
                    ok.append(r)

        dt = time.time() - t0
        total_proxies = sum(r.get("proxy_count", 0) for r in ok)
        print("\n" + "=" * 52)
        print(f"  完成 {len(ok)}/{count}  ·  用时 {dt:.0f}s  ·  代理共 {total_proxies} 个")
        print(f"  账号 → {acc_file}")
        print(f"  代理 → {node_file}")

        print("=" * 52 + "\n")
        return len(ok) == count
    finally:
        mail.session.close()


def _positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nodes · Cloud Mail 3.0.0 版本")
    command = parser.add_mutually_exclusive_group()
    command.add_argument("--count", type=_positive_int, help="本轮注册数量；省略则进入交互模式")
    command.add_argument("--resume", metavar="EMAIL", help="继续已保存且邮箱已验证账号的代理导出")
    parser.add_argument("--threads", type=_positive_int, default=3, help="并发数，默认 3，最多 8")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--hide-browser", dest="hidden", action="store_true", help="隐藏浏览器窗口")
    mode.add_argument("--show-browser", dest="hidden", action="store_false", help="显示浏览器窗口")
    parser.set_defaults(hidden=True)
    parser.add_argument(
        "--attempts", type=_positive_int, default=3, help="每个任务最多尝试次数，默认 3"
    )
    parser.add_argument("--mail-timeout", type=_positive_int, default=180, help="收信超时秒数")
    parser.add_argument(
        "--challenge-timeout", type=_positive_int, default=120, help="浏览器验证超时秒数"
    )
    command.add_argument(
        "--check-mail", action="store_true", help="仅检查 Cloud Mail 登录及主邮箱收信接口"
    )
    args = parser.parse_args(argv)
    try:
        if args.resume:
            return 0 if resume_account(args.resume) else 1
        config = load_config(_BASE)
        missing = [
            key.upper()
            for key in (
                "cloud_mail_url",
                "cloud_mail_email",
                "cloud_mail_password",
            )
            if not config[key]
        ]
        if missing:
            raise ValueError("缺少 Cloud Mail 配置: " + ", ".join(missing))
        if args.check_mail:
            mail = CloudMail(
                config["cloud_mail_url"],
                config["cloud_mail_email"],
                config["cloud_mail_password"],
            )
            try:
                rows = mail.list_messages(config["cloud_mail_email"])
                log(f"Cloud Mail 接口正常，当前返回 {len(rows)} 封邮件")
            finally:
                mail.session.close()
            return 0
        kwargs = {
            "max_attempts": args.attempts,
            "mail_timeout": args.mail_timeout,
            "challenge_timeout": args.challenge_timeout,
        }
        if args.count is not None:
            success = run_round(
                args.count,
                min(args.threads, args.count, 8),
                args.hidden,
                config,
                **kwargs,
            )
            return 0 if success else 1
        if not sys.stdin.isatty():
            parser.error("非交互环境必须指定 --count、--resume 或 --check-mail")
        while True:
            count, threads, headless = guide()
            if count <= 0:
                return 0
            run_round(count, threads, headless, config, **kwargs)
    except KeyboardInterrupt:
        log("操作已中断")
        return 130
    except Exception as exc:
        log(f"[x] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
