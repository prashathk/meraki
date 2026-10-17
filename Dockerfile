FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_FIREBASE_CONFIG={}
ENV VITE_FIREBASE_CONFIG=$VITE_FIREBASE_CONFIG
RUN npm run build
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY backend/requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend/ /app/backend/
COPY worker/ /app/worker/
COPY scripts/ /app/scripts/
COPY alembic.ini /app/
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 meraki && mkdir -p /app/data && chown -R meraki:meraki /app/data
USER meraki
EXPOSE 8080
CMD ["python","-m","uvicorn","backend.meraki.app:app","--host","0.0.0.0","--port","8080"]
