FROM node:20-alpine

WORKDIR /app

# Установка зависимостей
COPY frontend/login_page/package*.json ./
RUN npm install

# Копирование приложения
COPY frontend/login_page .

# Запуск dev сервера
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
