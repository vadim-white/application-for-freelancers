FROM python:3.14-slim

# без .pyc и с немедленным выводом логов
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Установка зависимостей
COPY gateway-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY gateway-service .

# Непривилегированный пользователь; код принадлежит root и процессу доступен только на чтение.
# USER числом, а не именем: kubelet проверяет runAsNonRoot только по числовому UID (имя не резолвит)
RUN useradd --system --uid 10001 --no-create-home app
USER 10001

# Запуск сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
