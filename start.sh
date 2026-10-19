#!/bin/sh
set -eu

cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    python=.venv/bin/python
else
    python=python3
fi

if [ "$(uname -s)" = Linux ] && [ -z "${DISPLAY:-}" ]; then
    if ! command -v xvfb-run >/dev/null 2>&1; then
        printf '%s\n' 'Linux 未设置 DISPLAY，请先安装 chromium xvfb xauth。' >&2
        exit 1
    fi
    exec xvfb-run -a -s '-screen 0 1280x900x24' "$python" proxyscrape_register.py "$@"
fi
exec "$python" proxyscrape_register.py "$@"
