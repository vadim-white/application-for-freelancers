#!/usr/bin/env bash
# Деплой в локальный кластер kind "freelance" в нужном порядке (аналог docker compose up --wait):
#   1. удалить старые Job миграций и seed (Job неизменяем, повторный apply изменённого падает);
#   2. kubectl apply -k k8s/overlays/local;
#   3. дождаться Job auth-migrate, task-migrate, time-migrate (Complete; при Failed — выход с логом);
#   4. применить k8s/overlays/local-seed и дождаться Job auth-seed (тестовые пользователи);
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
SEED="$ROOT/k8s/overlays/local-seed"
MIGRATIONS="auth-migrate task-migrate time-migrate"
JOB_TIMEOUT="${JOB_TIMEOUT:-300}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-180s}"
ENTRY_GATEWAY="entry"
ENTRY_URL="http://127.0.0.1:8080"
# ВРЕМЕННО, убрать в 1.4.7: политика закрывает DNS (kube-dns в kube-system), Job и сервисы не резолвят имена
BROKEN_NETPOL="freelance-service-netpol"

k() { kubectl --context "$CONTEXT" "$@"; }
die() { echo "ОШИБКА: $*" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "не найден kubectl"
kubectl config get-contexts -o name 2>/dev/null | grep -qx "$CONTEXT" \
  || die "нет контекста $CONTEXT — создайте кластер: ./scripts/kind-up.sh"
k get --raw /readyz >/dev/null 2>&1 || die "кластер $CONTEXT не отвечает (запущен ли Docker? ./scripts/kind-up.sh)"
# Gateway и HTTPRoute — CRD, их ставит Envoy Gateway в kind-up.sh; без них apply упадёт посередине
k get crd gateways.gateway.networking.k8s.io >/dev/null 2>&1 \
  && k -n envoy-gateway-system get deployment envoy-gateway >/dev/null 2>&1 \
  || die "в кластере нет Envoy Gateway — выполните ./scripts/kind-up.sh"
for f in app.env db.env; do
  [ -f "$OVERLAY/$f" ] || die "нет k8s/overlays/local/$f — создайте секреты: ./scripts/init-k8s-env.sh"
done

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

# ВРЕМЕННО, убрать в 1.4.7. Вызывается после каждого apply: оба apply создают политику заново
drop_broken_netpol() {
  if k -n "$NS" get networkpolicy "$BROKEN_NETPOL" >/dev/null 2>&1; then
    echo "ВНИМАНИЕ: удаляю NetworkPolicy $BROKEN_NETPOL — она закрывает DNS (временно, исправляется в шаге 1.4.7)" >&2
    k -n "$NS" delete networkpolicy "$BROKEN_NETPOL"
  fi
}

# 1. старые Job: тот же манифест после пересборки образа нужно выполнить заново, а изменённый — не применить
if k get namespace "$NS" >/dev/null 2>&1; then
  k -n "$NS" delete job -l 'app.kubernetes.io/component in (migration,seed)' --ignore-not-found --wait=true
fi

# 2. манифесты
k apply -k "$OVERLAY"

drop_broken_netpol

# 3. миграции (поды Job, стартовавшие до готовности БД, повторяются по backoffLimit)
# shellcheck disable=SC2086
wait_jobs $MIGRATIONS

# 4. тестовые пользователи: после миграций auth, отдельным apply (в одном apply порядка нет)
k apply -k "$SEED"
drop_broken_netpol
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

echo "Готово: миграции и seed выполнены, сервисы готовы. Вход: $ENTRY_URL (API — $ENTRY_URL/api)"
