FROM python:3.12-alpine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 DATABASE_PATH=/app/data/logs.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && adduser -D -u 10001 appuser && mkdir data && chown appuser:appuser data
COPY app.py storage.py ./
COPY static ./static
USER appuser
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --access-logfile - --error-logfile - app:application"]
