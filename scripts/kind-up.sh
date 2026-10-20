#!/usr/bin/env bash
# Поднимает локальный кластер kind "freelance", ставит в него Envoy Gateway (вход через
# Gateway API) и загружает образы сервисов.
# Идемпотентен: существующий кластер не пересоздаётся, Envoy Gateway применяется повторно без
# изменений, образы пересобираются и загружаются заново. Манифесты приложения не применяет,
# значения секретов не нужны.
# Совместим с macOS bash 3.2.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER="freelance"
CONTEXT="kind-$CLUSTER"
IMAGES="ser-auth ser-task ser-time ser-gateway ser-frontend"
# Envoy Gateway — контроллер входа (Gateway API). install.yaml релиза содержит CRD Gateway API той же
# версии (v1.6.1, канал experimental), CRD Envoy Gateway и контроллер в envoy-gateway-system.
# Версия и sha256 файла закреплены: другой файл по тому же адресу не применится.
ENVOY_GATEWAY_VERSION="v1.9.2"
ENVOY_GATEWAY_SHA256="0412a72907e57ff9b73c56a7bf6df5190bf0f6e4f8bb4bba34e38630bbab5778"
ENVOY_GATEWAY_URL="https://github.com/envoyproxy/gateway/releases/download/$ENVOY_GATEWAY_VERSION/install.yaml"

for tool in docker kind kubectl curl git; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден $tool (kind: brew install kind)" >&2; exit 1; }
done

# sha256 файла: shasum на macOS, sha256sum на Linux (CI)
sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

cd "$ROOT"

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  echo "Кластер $CLUSTER уже есть, пропускаю создание"
else
  kind create cluster --config k8s/kind-config.yaml
fi

# kind создаёт узел с restart=on-failure: после перезапуска Docker Desktop кластер сам поднимается
# и держит ~2 ГиБ. Выключаем автозапуск: кластер стартует только вручную (docker start)
docker update --restart=no "$CLUSTER-control-plane" >/dev/null

kubectl --context "$CONTEXT" wait --for=condition=Ready node --all --timeout=120s

# Envoy Gateway: server-side apply (CRD слишком велики для аннотации last-applied client-side apply),
# повторное применение того же файла ничего не меняет
eg_tmp="$(mktemp)"
trap 'rm -f "$eg_tmp"' EXIT
curl -fsSL -o "$eg_tmp" "$ENVOY_GATEWAY_URL"
[ "$(sha256 "$eg_tmp")" = "$ENVOY_GATEWAY_SHA256" ] \
  || { echo "sha256 $ENVOY_GATEWAY_URL не совпадает с закреплённым" >&2; exit 1; }
kubectl --context "$CONTEXT" apply --server-side -f "$eg_tmp"
kubectl --context "$CONTEXT" -n envoy-gateway-system wait --for=condition=Available \
  deployment/envoy-gateway --timeout=300s

# сборка образов из docker-compose.yml (теги ser-*:latest).
# compose разбирает файл целиком и требует SECRET_KEY и пароли баз, хотя сборке они
# не нужны: подставляем заглушки только в окружение этой команды (в образы не попадают,
# .env не читается и не создаётся)
SECRET_KEY=build AUTH_DB_PASSWORD=build TASK_DB_PASSWORD=build TIME_DB_PASSWORD=build \
  docker compose build

# Тег по коммиту, а не :latest: новый тег меняет спецификацию подов, и k8s-deploy.sh их перекатывает.
# Время в -dirty — чтобы каждая сборка с незакоммиченными правками получала свой тег.
TAG="$(git rev-parse --short=12 HEAD)"
changes="$(git status --porcelain)"
if [ -n "$changes" ]; then
  TAG="$TAG-dirty-$(date +%Y%m%d%H%M%S)"
fi

# на хосте тег нужен только на время kind load; compose по-прежнему работает с :latest
for image in $IMAGES; do
  docker tag "$image:latest" "$image:$TAG"
  kind load docker-image --name "$CLUSTER" "$image:$TAG"
  docker image rm "$image:$TAG" >/dev/null
done
printf '%s\n' "$TAG" > k8s/overlays/local/image-tag

# Старые теги ser-* в узле — по одной ссылке через ctr: crictl rmi снимает все теги с тем же ID,
# в том числе текущий, если образ между сборками не менялся. Теги работающих подов не трогаем.
NODE="$CLUSTER-control-plane"
# CRI узнаёт о загруженных образах асинхронно; без этого новый образ мог бы не попасть в keep ниже
for image in $IMAGES; do
  tries=0
  until docker exec "$NODE" crictl inspecti "$image:$TAG" >/dev/null 2>&1; do
    tries=$((tries + 1))
    [ "$tries" -lt 30 ] || { echo "CRI в узле не видит $image:$TAG" >&2; exit 1; }
    sleep 1
  done
done
in_use="$(kubectl --context "$CONTEXT" get pods -A \
  -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{end}')"
refs="$(docker exec "$NODE" ctr -n k8s.io images ls -q)"
imports=""
for ref in $refs; do
  case "$ref" in
    import-*@sha256:*) imports="$imports $ref"; continue ;;
    *@*) continue ;;
    docker.io/library/ser-*:*) ;;
    *) continue ;;
  esac
  name="${ref#docker.io/library/}"
  [ "${name##*:}" = "$TAG" ] && continue
  printf '%s\n' "$in_use" | grep -qxF "$name" && continue
  docker exec "$NODE" ctr -n k8s.io images rm "$ref" >/dev/null
  echo "Удалён из узла старый образ $name"
done
# Содержимое снятых образов держат ещё import-<дата>@sha256 (от kind load) и sha256:<ID> (от CRI): удаляем
# через ctr (crictl rmi import-ссылки не находит), с --sync — иначе сборка мусора откладывается.
keep="$(docker exec "$NODE" crictl images --no-trunc \
  | awk 'NR > 1 && $1 != "<none>" && $1 !~ /^docker\.io\/library\/import-/ { print $3 }')"
orphans=""
for ref in $refs; do
  case "$ref" in
    sha256:*) printf '%s\n' "$keep" | grep -qxF "$ref" || orphans="$orphans $ref" ;;
  esac
done
if [ -n "$imports$orphans" ]; then
  # shellcheck disable=SC2086
  docker exec "$NODE" ctr -n k8s.io images rm --sync $imports $orphans >/dev/null
fi

echo "Готово. Кластер $CLUSTER, контекст $CONTEXT, Envoy Gateway $ENVOY_GATEWAY_VERSION, образы: $IMAGES, тег $TAG"
