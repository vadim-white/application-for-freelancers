#!/usr/bin/env bash
# Поднимает локальный кластер kind "freelance" и загружает в него образы сервисов.
# Идемпотентен: существующий кластер не пересоздаётся, образы пересобираются
# и загружаются заново. Манифесты не применяет, значения секретов не нужны.
# Совместим с macOS bash 3.2.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER="freelance"
CONTEXT="kind-$CLUSTER"
IMAGES="ser-auth ser-task ser-time ser-gateway ser-frontend"

for tool in docker kind kubectl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден $tool (kind: brew install kind)" >&2; exit 1; }
done

cd "$ROOT"

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  echo "Кластер $CLUSTER уже есть, пропускаю создание"
else
  kind create cluster --config k8s/kind-config.yaml
fi

kubectl --context "$CONTEXT" wait --for=condition=Ready node --all --timeout=120s

# сборка образов из docker-compose.yml (теги ser-*:latest, как в манифестах).
# compose разбирает файл целиком и требует SECRET_KEY и пароли баз, хотя сборке они
# не нужны: подставляем заглушки только в окружение этой команды (в образы не попадают,
# .env не читается и не создаётся)
SECRET_KEY=build AUTH_DB_PASSWORD=build TASK_DB_PASSWORD=build TIME_DB_PASSWORD=build \
  docker compose build

for image in $IMAGES; do
  kind load docker-image --name "$CLUSTER" "$image:latest"
done

echo "Готово. Кластер $CLUSTER, контекст $CONTEXT, образы: $IMAGES"
