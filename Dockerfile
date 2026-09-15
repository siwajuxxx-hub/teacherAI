# syntax=docker/dockerfile:1
# ─── Единый образ: React-SPA (static) + FastAPI (one origin, без CORS) ───
# Этап 1: сборка фронтенда
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Этап 2: backend + собранный dist
FROM python:3.12-slim
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

# Только пакет app — данные и секреты в образ не попадают
COPY backend/app ./app
COPY --from=web /web/dist ./static

# SQLite-каталог: в свежем контейнере базы создаются и сидируются сами (app.main.lifespan)
RUN mkdir -p /app/backend/data

EXPOSE 8000

# Render/Koyeb передают порт в $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
