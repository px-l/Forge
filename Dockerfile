FROM node:22-slim AS web
WORKDIR /web
COPY forge/package*.json ./
RUN npm ci
COPY forge/index.html forge/vite.config.ts forge/tsconfig.json ./
COPY forge/src ./src
COPY forge/public ./public
RUN npm run build
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY --from=web /web/dist ./forge/dist
RUN useradd -m forge && mkdir /app/data && chown forge:forge /app/data
USER forge
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8010"]
