# KRONOS image: website + API. PostgreSQL (pgvector) and the local AI (Ollama) run as separate services — see docker-compose.yml.
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 TZ=Asia/Kolkata
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
# CPU build of PyTorch (the GNN is small); avoids a multi-GB CUDA download
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist /app/frontend/dist
COPY docker/entrypoint.py /app/entrypoint.py
ENV KRONOS_STATIC_DIR=/app/frontend/dist
EXPOSE 8000
CMD ["python", "/app/entrypoint.py"]
