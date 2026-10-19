#!/bin/sh
set -eu

cd "$(dirname "$0")"
mkdir -p account node
container="nodes-export-$(date +%Y%m%d%H%M%S)-$$"
printf '运行容器：%s\n' "$container"

status=0
docker compose run --no-deps --name "$container" nodes "$@" || status=$?

# 先复制到临时目录，避免 Docker 与本机共享目录时边读边覆盖同一文件。
output=$(mktemp -d "${TMPDIR:-/tmp}/nodes-output.XXXXXX")
if docker cp "$container:/app/account" "$output/account" \
    && docker cp "$container:/app/node" "$output/node" \
    && cp -R "$output/account/." account/ \
    && cp -R "$output/node/." node/; then
    rm -rf "$output"
    docker rm "$container" >/dev/null
    printf '账号已保存到：%s/account/\n节点已保存到：%s/node/\n' "$PWD" "$PWD"
else
    printf '输出复制失败，已保留容器 %s 和临时目录 %s。\n' "$container" "$output" >&2
    printf '可手动取出节点：docker cp %s:/app/node/. ./node/\n' "$container" >&2
    exit 1
fi
exit "$status"
