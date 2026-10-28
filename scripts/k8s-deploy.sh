#!/usr/bin/env bash
# Деплой в kind по порядку, как docker compose up --wait: миграции, seed, rollout, вход.
# Кластер и образы готовит kind-up.sh, секреты — init-k8s-env.sh. Совместим с macOS bash 3.2.
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
# HPA применится и без metrics-server, но не будет масштабировать (TARGETS <unknown>) — лучше отказать сразу
k -n kube-system get deployment metrics-server >/dev/null 2>&1 \
  || die "в кластере нет metrics-server (нужен HPA) — выполните ./scripts/kind-up.sh"
for f in app.env db.env; do
  [ -f "$OVERLAY/$f" ] || die "нет k8s/overlays/local/$f — создайте секреты: ./scripts/init-k8s-env.sh"
done
[ -f "$OVERLAY/image-tag" ] || die "нет k8s/overlays/local/image-tag — выполните ./scripts/kind-up.sh"
TAG="$(cat "$OVERLAY/image-tag")"
case "$TAG" in
  ""|*[!A-Za-z0-9._-]*) die "некорректный тег в k8s/overlays/local/image-tag — выполните ./scripts/kind-up.sh" ;;
esac
# image-registry пишет kind-up.sh в режиме реестра (IMAGE_REGISTRY), в обычном режиме его нет
REGISTRY=""
if [ -f "$OVERLAY/image-registry" ]; then
  REGISTRY="$(cat "$OVERLAY/image-registry")"
  case "$REGISTRY" in
    ""|/*|*/|*[!a-z0-9./:_-]*) die "некорректный реестр в k8s/overlays/local/image-registry — выполните ./scripts/kind-up.sh" ;;
  esac
fi
# Тег должен быть собран из текущего дерева: иначе (например, docker start узла без kind-up.sh)
# в кластер молча встают образы прошлого коммита. ALLOW_STALE_TAG=1 — выкатить такой тег намеренно.
stale=""
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  head="$(git -C "$ROOT" rev-parse --short=12 HEAD)"
  if [ -z "$(git -C "$ROOT" status --porcelain)" ]; then
    [ "$TAG" = "$head" ] || stale="дерево чистое, HEAD $head"
  else
    case "$TAG" in
      "$head"-dirty-*)
        # правки после сборки: файл новее image-tag, который kind-up.sh пишет после загрузки образов
        # shellcheck disable=SC2016
        newer="$(cd "$ROOT" && git ls-files -m -o --exclude-standard -z \
          | xargs -0 sh -c 'for f; do [ "$f" -nt "$0" ] && echo "$f"; done' "$OVERLAY/image-tag" | head -n 3)"
        [ -z "$newer" ] || stale="файлы изменены после сборки: $(echo "$newer" | paste -sd ' ' -)" ;;
      *) stale="в дереве незакоммиченные правки поверх HEAD $head" ;;
    esac
  fi
fi
if [ -n "$stale" ]; then
  if [ "${ALLOW_STALE_TAG:-}" = 1 ]; then
    echo "ПРЕДУПРЕЖДЕНИЕ: тег $TAG не соответствует рабочему дереву ($stale), ALLOW_STALE_TAG=1 — выкатываю" >&2
  elif [ -n "$REGISTRY" ]; then
    # kind-up.sh в режиме реестра ничего не собирает: его повтор дал бы ту же ошибку
    die "тег $TAG из image-tag не соответствует рабочему дереву ($stale) — образы из реестра собраны CI из коммита $TAG, а манифесты берутся из дерева: уберите правки и лишние файлы (git status), тег HEAD — IMAGE_REGISTRY=$REGISTRY ./scripts/kind-up.sh; выкатить намеренно — ALLOW_STALE_TAG=1"
  else
    die "тег $TAG из image-tag не соответствует рабочему дереву ($stale) — выполните ./scripts/kind-up.sh (выкатить этот тег намеренно: ALLOW_STALE_TAG=1)"
  fi
fi
if [ -n "$REGISTRY" ]; then
  # без тега в реестре под висел бы в ImagePullBackOff до таймаута rollout; манифест — без скачивания слоёв
  for image in $IMAGES; do
    docker manifest inspect "$REGISTRY/$image:$TAG" >/dev/null 2>&1 \
      || die "в реестре нет образа $REGISTRY/$image:$TAG или реестр недоступен (публикует CI на push в main, коммит с [skip ci] не публикуется; опубликованный тег: IMAGE_REGISTRY=$REGISTRY IMAGE_TAG=<SHA 12> ./scripts/kind-up.sh)"
  done
else
  # с imagePullPolicy: Never под без образа в узле висит в ErrImageNeverPull до таймаута rollout
  for image in $IMAGES; do
    docker exec "$NODE" crictl inspecti "$image:$TAG" >/dev/null 2>&1 \
      || die "в узле kind нет образа $image:$TAG — выполните ./scripts/kind-up.sh"
  done
fi

# write_kustomization <каталог> <overlay>: overlay из git с подставленным тегом образов.
# Тег в кавычках: короткий SHA из одних цифр или вида 1234e567 YAML прочёл бы как число.
# В режиме реестра — ещё имя образа в реестре и IfNotPresent поверх Never (overlays/local и auth-seed.yaml):
# узел скачивает образ один раз, тег по SHA не меняет содержимое.
write_kustomization() {
  mkdir -p "$DEPLOY_DIR/$1"
  {
    printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n'
    printf 'resources:\n  - ../../%s\nimages:\n' "$2"
    for image in $IMAGES; do
      printf '  - name: %s\n' "$image"
      [ -z "$REGISTRY" ] || printf '    newName: %s/%s\n' "$REGISTRY" "$image"
      printf '    newTag: "%s"\n' "$TAG"
    done
    if [ -n "$REGISTRY" ]; then
      printf 'patches:\n'
      for kind in Deployment Job; do
        printf '  - target:\n      kind: %s\n    patch: |-\n' "$kind"
        printf '      - op: replace\n        path: /spec/template/spec/containers/0/imagePullPolicy\n        value: IfNotPresent\n'
      done
    fi
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

# Job неизменяем: изменённый манифест не применится, а тот же после пересборки не выполнится заново
if k get namespace "$NS" >/dev/null 2>&1; then
  k -n "$NS" delete job -l 'app.kubernetes.io/component in (migration,seed)' --ignore-not-found --wait=true
fi

k apply -k "$DEPLOY_DIR/app"

# поды Job, стартовавшие до готовности БД, повторяются по backoffLimit
# shellcheck disable=SC2086
wait_jobs $MIGRATIONS

# seed — отдельным apply после миграций auth: внутри одного apply порядка нет
k apply -k "$DEPLOY_DIR/seed"
wait_jobs auth-seed

# списки — отдельным присваиванием: сбой kubectl внутри for $(…) set -e не ловит
statefulsets="$(k -n "$NS" get statefulset -o name)"
deployments="$(k -n "$NS" get deployment -o name)"
for sts in $statefulsets; do
  k -n "$NS" rollout status "$sts" --timeout="$ROLLOUT_TIMEOUT"
done
for deploy in $deployments; do
  k -n "$NS" rollout status "$deploy" --timeout="$ROLLOUT_TIMEOUT"
done

# Programmed: прокси Envoy получил маршруты, вход открыт
k -n "$NS" wait --for=condition=Programmed "gateway/$ENTRY_GATEWAY" --timeout="$ROLLOUT_TIMEOUT"

echo "Готово: миграции и seed выполнены, сервисы готовы (образы ${REGISTRY:+$REGISTRY/ser-*}:$TAG). Вход: $ENTRY_URL (API — $ENTRY_URL/api)"
