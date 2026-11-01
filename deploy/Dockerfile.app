# Server deployment uses an official mirror and the locally verified frontend build.
FROM public.ecr.aws/docker/library/python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY forge/dist ./forge/dist
RUN useradd -u 10001 -m forge && mkdir /app/data && chown forge:forge /app/data
USER forge
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8010","--proxy-headers","--forwarded-allow-ips=127.0.0.1"]
