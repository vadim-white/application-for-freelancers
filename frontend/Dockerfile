# Сборка: npm ci по package-lock.json, затем vite build в /app/dist
FROM node:24-alpine AS build

WORKDIR /app

COPY frontend/login_page/package.json frontend/login_page/package-lock.json ./
RUN npm ci

COPY frontend/login_page .
RUN npm run build

# Раздача: nginx без root (uid 101), слушает 8080; /api/ проксирует на gateway.
# Шаблон из /etc/nginx/templates при старте превращается в /etc/nginx/conf.d/default.conf (envsubst),
# подставляются только GATEWAY_URL (задаётся при запуске) и NGINX_LOCAL_RESOLVERS
# (образ вычисляет его из /etc/resolv.conf только при NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1)
FROM nginxinc/nginx-unprivileged:alpine

ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENVSUBST_FILTER="^(GATEWAY_URL|NGINX_LOCAL_RESOLVERS)$"

# файлы принадлежат root, nginx их только читает
COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
