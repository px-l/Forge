FROM python:3.11-slim
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn playwright==1.64.1 && playwright install --with-deps chromium && chmod -R a+rX /ms-playwright
COPY runner /app/runner
RUN useradd -m runner
USER runner
CMD ["uvicorn","runner.main:app","--host","0.0.0.0","--port","8011"]
