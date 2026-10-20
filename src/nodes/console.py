"""Thread-aware console output shared by services and workflows."""

import threading
import time

_print_lock = threading.Lock()
_tls = threading.local()


def set_worker(idx):
    _tls.tag = f" #{idx}"


def log(msg):
    tag = getattr(_tls, "tag", "")
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}]{tag} {msg}", flush=True)
