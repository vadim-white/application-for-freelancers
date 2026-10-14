FROM python:3.14-slim

WORKDIR /app

# Установка зависимостей
COPY task-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY task-service .

# Запуск сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
