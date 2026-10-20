#!/usr/bin/env bash
# Деплой в локальный кластер kind "freelance" в нужном порядке (аналог docker compose up --wait):
#   1. удалить старые Job миграций и seed (Job неизменяем, повторный apply изменённого падает);
#   2. kubectl apply -k k8s/overlays/.deploy/app (overlay local с тегом образов из image-tag);
#   3. дождаться Job auth-migrate, task-migrate, time-migrate (Complete; при Failed — выход с логом);
#   4. применить k8s/overlays/.deploy/seed (local-seed с тем же тегом) и дождаться Job auth-seed;
#   5. rollout status баз (StatefulSet) и сервисов (Deployment);
#   6. дождаться Gateway entry (Programmed: Envoy получил конфигурацию, вход на http://127.0.0.1:8080).
# Код возврата ≠ 0 при любом сбое. Кластер и образы готовит scripts/kind-up.sh,
# секреты — scripts/init-k8s-env.sh. Работает только с контекстом kind-freelance.
# Совместим с macOS bash 3.2.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTEXT="kind-freelance"
NS="freelance-service"
OVERLAY="$ROOT/k8s/overlays/local"
DEPLOY_DIR="$ROOT/k8s/overlays/.deploy"
NODE="freelance-control-plane"
IMAGES="ser-auth ser-task ser-time ser-gateway ser-frontend"
MIGRATIONS="auth-migrate task-migrate time-migrate"
JOB_TIMEOUT="${JOB_TIMEOUT:-300}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-180s}"
ENTRY_GATEWAY="entry"
ENTRY_URL="http://127.0.0.1:8080"

k() { kubectl --context "$CONTEXT" "$@"; }
die() { echo "ОШИБКА: $*" >&2; exit 1; }

for tool in kubectl docker; do
  command -v "$tool" >/dev/null 2>&1 || die "не найден $tool"
done
kubectl config get-contexts -o name 2>/dev/null | grep -qx "$CONTEXT" \
  || die "нет контекста $CONTEXT — создайте кластер: ./scripts/kind-up.sh"
k get --raw /readyz >/dev/null 2>&1 || die "кластер $CONTEXT не отвечает (запущен ли Docker? ./scripts/kind-up.sh)"
# Gateway и HTTPRoute — CRD, их ставит Envoy Gateway в kind-up.sh; без них apply упадёт посередине
if ! k get crd gateways.gateway.networking.k8s.io >/dev/null 2>&1 \
  || ! k -n envoy-gateway-system get deployment envoy-gateway >/dev/null 2>&1; then
  die "в кластере нет Envoy Gateway — выполните ./scripts/kind-up.sh"
fi
for f in app.env db.env; do
  [ -f "$OVERLAY/$f" ] || die "нет k8s/overlays/local/$f — создайте секреты: ./scripts/init-k8s-env.sh"
done
[ -f "$OVERLAY/image-tag" ] || die "нет k8s/overlays/local/image-tag — выполните ./scripts/kind-up.sh"
TAG="$(cat "$OVERLAY/image-tag")"
case "$TAG" in
  ""|*[!A-Za-z0-9._-]*) die "некорректный тег в k8s/overlays/local/image-tag — выполните ./scripts/kind-up.sh" ;;
esac
# с imagePullPolicy: Never под без образа в узле висит в ErrImageNeverPull до таймаута rollout
for image in $IMAGES; do
  docker exec "$NODE" crictl inspecti "$image:$TAG" >/dev/null 2>&1 \
    || die "в узле kind нет образа $image:$TAG — выполните ./scripts/kind-up.sh"
done

# write_kustomization <каталог> <overlay>: overlay из git с подставленным тегом образов.
# Тег в кавычках: короткий SHA из одних цифр или вида 1234e567 YAML прочёл бы как число.
write_kustomization() {
  mkdir -p "$DEPLOY_DIR/$1"
  {
    printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n'
    printf 'resources:\n  - ../../%s\nimages:\n' "$2"
    for image in $IMAGES; do
      printf '  - name: %s\n    newTag: "%s"\n' "$image" "$TAG"
    done
  } > "$DEPLOY_DIR/$1/kustomization.yaml"
}
write_kustomization app local
write_kustomization seed local-seed

# wait_jobs <job>...: ждать Complete у всех Job; Failed или таймаут — лог Job и выход с ошибкой
wait_jobs() {
  deadline=$(( $(date +%s) + JOB_TIMEOUT ))
  for job in "$@"; do
    while :; do
      conds="$(k -n "$NS" get job "$job" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type} {end}')"
      case " $conds " in
        *" Complete "*) echo "Job $job: Complete"; break ;;
        *" Failed "*|*" FailureTarget "*)
          k -n "$NS" logs "job/$job" --tail=30 >&2 || true
          die "Job $job завершился с ошибкой (лог выше; подробнее: kubectl --context $CONTEXT -n $NS describe job $job)" ;;
      esac
      if [ "$(date +%s)" -ge "$deadline" ]; then
        k -n "$NS" logs "job/$job" --tail=30 >&2 || true
        die "Job $job не завершился за ${JOB_TIMEOUT} с"
      fi
      sleep 2
    done
  done
}

# 1. старые Job: тот же манифест после пересборки образа нужно выполнить заново, а изменённый — не применить
if k get namespace "$NS" >/dev/null 2>&1; then
  k -n "$NS" delete job -l 'app.kubernetes.io/component in (migration,seed)' --ignore-not-found --wait=true
fi

# 2. манифесты
k apply -k "$DEPLOY_DIR/app"

# 3. миграции (поды Job, стартовавшие до готовности БД, повторяются по backoffLimit)
# shellcheck disable=SC2086
wait_jobs $MIGRATIONS

# 4. тестовые пользователи: после миграций auth, отдельным apply (в одном apply порядка нет)
k apply -k "$DEPLOY_DIR/seed"
wait_jobs auth-seed

# 5. базы и сервисы
# списки — отдельным присваиванием: сбой kubectl внутри for $(…) set -e не ловит
statefulsets="$(k -n "$NS" get statefulset -o name)"
deployments="$(k -n "$NS" get deployment -o name)"
for sts in $statefulsets; do
  k -n "$NS" rollout status "$sts" --timeout="$ROLLOUT_TIMEOUT"
done
for deploy in $deployments; do
  k -n "$NS" rollout status "$deploy" --timeout="$ROLLOUT_TIMEOUT"
done

# 6. вход: Envoy Gateway создаёт прокси в envoy-gateway-system и программирует его маршрутами
k -n "$NS" wait --for=condition=Programmed "gateway/$ENTRY_GATEWAY" --timeout="$ROLLOUT_TIMEOUT"

echo "Готово: миграции и seed выполнены, сервисы готовы (образы :$TAG). Вход: $ENTRY_URL (API — $ENTRY_URL/api)"
