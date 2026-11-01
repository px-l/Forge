# Server deployment uses an official mirror and the locally verified frontend build.
FROM public.ecr.aws/docker/library/python:3.11-slim
RUN sed -i 's|http://deb.debian.org|http://mirrors.tencentyun.com|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 update && apt-get install -y --no-install-recommends openssh-client git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN sed '/^playwright==/d' requirements.txt > /tmp/app-requirements.txt && pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple -r /tmp/app-requirements.txt
COPY backend ./backend
COPY forge/dist ./forge/dist
RUN useradd -u 10001 -m forge && mkdir /app/data && chown forge:forge /app/data
USER forge
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8010","--proxy-headers","--forwarded-allow-ips=127.0.0.1"]
