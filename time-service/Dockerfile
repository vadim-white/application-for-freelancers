FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY time-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

# Копирование приложения
COPY time-service .

# Запуск сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
