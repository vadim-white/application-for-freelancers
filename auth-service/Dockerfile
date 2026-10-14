FROM python:3.14-slim

# без .pyc и с немедленным выводом логов
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Установка зависимостей
COPY auth-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY auth-service .

# Непривилегированный пользователь; код принадлежит root и процессу доступен только на чтение
RUN useradd --system --uid 10001 --no-create-home app
USER app

# Запуск сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
