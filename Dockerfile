FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BROWSER_PATH=/usr/bin/chromium

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium xvfb xauth fonts-liberation tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && mkdir -p account node

STOPSIGNAL SIGINT

ENTRYPOINT ["/usr/bin/tini", "-s", "-g", "--", "xvfb-run", "-a", "-s", "-screen 0 1280x900x24"]
CMD ["nodes", "--count", "1", "--threads", "1", "--hide-browser"]
