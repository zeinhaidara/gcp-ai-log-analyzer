FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home agent
COPY service.py .
USER agent
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn service:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --no-access-log"]
