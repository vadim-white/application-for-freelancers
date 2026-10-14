FROM python:3.14-slim

WORKDIR /app

# Установка зависимостей
COPY gateway-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY gateway-service .

# Запуск сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
