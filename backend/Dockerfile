# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -r basjoo && useradd -r -g basjoo basjoo \
    && mkdir -p /app/data /app/.cache \
    && chown -R basjoo:basjoo /app/data /app/.cache

ENV HOME=/app

COPY --chown=basjoo:basjoo docker-entrypoint.py env_bootstrap.py /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.py /usr/local/bin/env_bootstrap.py

# Copy application code
COPY --chown=basjoo:basjoo . .

EXPOSE 8000

ENTRYPOINT ["python3", "/usr/local/bin/docker-entrypoint.py"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
