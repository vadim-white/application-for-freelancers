#!/bin/bash
# e2e-тесты (Playwright) в Docker: bash tests/e2e/run.sh [аргументы pytest]
# Адрес фронта — E2E_BASE_URL (по умолчанию http://127.0.0.1:5173 — compose; kind — http://127.0.0.1:8080).
# Стек уже должен быть поднят: скрипт его не запускает и готовности не ждёт.
# Образ freelance-e2e собирается из tests/e2e/Dockerfile (зависимости по uv.lock, слой кэшируется),
# тесты монтируются в контейнер; скриншоты и trace упавших тестов — в tests/e2e/test-results/.
# Сеть: на Linux — --network host (127.0.0.1 контейнера = хост). На macOS (Docker Desktop) host-сети
# нет: внутри контейнера поднимается TCP-форвардер 127.0.0.1:<порт> -> host.docker.internal:<порт>,
# и браузер открывает тот же адрес, что и на хосте.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:5173}"
IMAGE=freelance-e2e

# хост и порт из адреса: http://127.0.0.1:5173/... -> 127.0.0.1 и 5173
SCHEME="${BASE_URL%%://*}"
HOSTPORT="${BASE_URL#*://}"; HOSTPORT="${HOSTPORT%%/*}"
HOST="${HOSTPORT%:*}"
if [ "$HOST" = "$HOSTPORT" ]; then
  PORT=$([ "$SCHEME" = https ] && echo 443 || echo 80)
else
  PORT="${HOSTPORT##*:}"
fi

docker build -q -t "$IMAGE" "$DIR" >/dev/null

# свой uid, чтобы test-results на Linux не принадлежали root; HOME — для кэшей браузера
RUN=(docker run --rm --init --ipc=host --user "$(id -u):$(id -g)" -e HOME=/tmp
  -e E2E_BASE_URL="$BASE_URL" -v "$DIR":/e2e -w /e2e)

FORWARD=0
if [ "$(uname -s)" = Linux ]; then
  RUN+=(--network host)
elif [ "$HOST" = 127.0.0.1 ] || [ "$HOST" = localhost ]; then
  FORWARD=1
fi

echo "e2e: $BASE_URL ($(uname -s), форвардер: $([ $FORWARD = 1 ] && echo "127.0.0.1:$PORT -> host.docker.internal:$PORT" || echo нет))"

if [ $FORWARD = 1 ]; then
  # форвардер в фоне; pytest стартует, когда порт уже слушается (до 5 с).
  # Одинарные кавычки намеренно: $FWD_PORT и "$@" раскрывает bash внутри контейнера
  # shellcheck disable=SC2016
  exec "${RUN[@]}" -e FWD_PORT="$PORT" "$IMAGE" bash -c '
    python forward.py "$FWD_PORT" host.docker.internal &
    for _ in $(seq 50); do (exec 3<>"/dev/tcp/127.0.0.1/$FWD_PORT") 2>/dev/null && break; sleep 0.1; done
    (exec 3<>"/dev/tcp/127.0.0.1/$FWD_PORT") 2>/dev/null || { echo "форвардер не слушает 127.0.0.1:$FWD_PORT" >&2; exit 1; }
    exec pytest "$@"' bash "$@"
else
  exec "${RUN[@]}" "$IMAGE" pytest "$@"
fi
