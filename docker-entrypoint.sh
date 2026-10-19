#!/bin/sh
set -eu

if [ "${1:-}" = python ] || [ "${1:-}" = python3 ]; then
    exec xvfb-run -a -s '-screen 0 1280x900x24' "$@"
fi
exec xvfb-run -a -s '-screen 0 1280x900x24' python proxyscrape_register.py "$@"
