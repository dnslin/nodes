FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BROWSER_PATH=/usr/bin/chromium

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium xvfb xauth fonts-liberation tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x start.sh docker-entrypoint.sh \
    && mkdir -p account node

ENTRYPOINT ["/usr/bin/tini", "-s", "-g", "--", "/app/docker-entrypoint.sh"]
CMD ["--count", "1", "--threads", "1", "--hide-browser"]
