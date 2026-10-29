FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_TIMEZONE=Asia/Gaza \
    DATA_DIR=/app/data \
    DATABASE_PATH=/app/data/saloon_dreem.db

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
RUN mkdir -p /app/data && useradd --create-home --uid 10001 saloon && chown -R saloon:saloon /app
USER saloon
EXPOSE 8000
CMD ["python", "-m", "backend.app.server_entry"]
