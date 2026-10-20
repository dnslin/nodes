"""Account snapshots and proxy files stored in the working directory."""

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

_file_lock = threading.Lock()


def timestamp():
    return time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000_000:09d}"


def new_round_files(root):
    root = Path(root)
    (root / "account").mkdir(exist_ok=True)
    (root / "node").mkdir(exist_ok=True)
    stamp = timestamp()
    return root / "account" / f"accounts_{stamp}.jsonl", root / "node" / f"proxies_{stamp}.txt"


def resume_proxy_file(root):
    directory = Path(root) / "node"
    directory.mkdir(exist_ok=True)
    return directory / f"proxies_resume_{timestamp()}.txt"


def find_account(root, email):
    directory = Path(root) / "account"
    for path in sorted(directory.glob("accounts_*.jsonl"), reverse=True):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if line.strip():
                record = json.loads(line)
                if record.get("email") == email:
                    return path, record
    raise ValueError(f"在 {directory} 中没有找到已保存的账号 {email}")


def _format_proxy_url(user, pwd, ip):
    return f"http://{quote(user, safe='')}:{quote(pwd, safe='')}@{ip}"


def save_proxies(user, pwd, proxies, path):
    """追加写入本轮代理文件，格式 http://user:pass@ip:port。"""
    with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            for ip in proxies:
                f.write(f"{_format_proxy_url(user, pwd, ip)}\n")


def save_account(rec, path):
    with _file_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
