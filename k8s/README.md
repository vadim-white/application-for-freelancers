# Kubernetes: локальный кластер kind

Инструкция по запуску приложения в Kubernetes. Кластер — [kind](https://kind.sigs.k8s.io/) (Kubernetes в Docker), один узел на этой машине. Манифесты собирает kustomize (встроен в kubectl), вход — Gateway API с контроллером [Envoy Gateway](https://gateway.envoyproxy.io/). Облачного варианта (реестр образов, TLS, управляемый Postgres) пока нет: [base](base) написана без локальных допущений, но overlay есть только для kind.

Docker Compose и кластер независимы: у них разные порты (compose — `127.0.0.1:5173` и `:8000`, кластер — `127.0.0.1:8080`) и разные секреты. Оба стека помещаются в 4 ГБ и могут работать одновременно. Но `docker compose up --build` рядом с работающим кластером отнимает у него CPU (см. «Известные ограничения»).

## Требования

| Что | Версия (проверено) | Зачем |
|---|---|---|
| Docker (Docker Desktop) | 28.5, Compose 2.40 | узел kind — контейнер, образы собирает `docker compose build` |
| Память Docker | 4 ГБ (3,8 ГиБ доступно) | узел kind с приложением занимает 2,1–2,5 ГиБ, compose рядом — ~0,4 ГиБ |
| kind | v0.33.0 (`brew install kind`) | создание кластера |
| kubectl | 1.34.1 (kustomize 5.7.1); в CI — v1.35.9 | версия сервера 1.35, в пределах ±1 минорной |
| curl | любая | `kind-up.sh` скачивает `install.yaml` Envoy Gateway |
| python3 или openssl | любая | `init-k8s-env.sh` генерирует секреты; без обоих скрипт завершается с кодом 1 |
| bash | 3.2+ (подходит системный macOS) | скрипты |

Нужен доступ в интернет: образ узла kind, `install.yaml` Envoy Gateway, образы Envoy и `postgres:15-alpine`. Порт `127.0.0.1:8080` на хосте должен быть свободен.

Закреплённые версии внешних компонентов:

| Компонент | Версия | Где закреплена |
|---|---|---|
| Узел kind | `kindest/node:v1.35.8@sha256:07b2536e…` | [kind-config.yaml](kind-config.yaml) |
| Envoy Gateway | v1.9.2 (`install.yaml`, sha256 сверяется) | [scripts/kind-up.sh](../scripts/kind-up.sh) |
| Gateway API CRD | v1.6.1 (из того же `install.yaml`) | там же |
| Envoy Proxy | distroless v1.39.1 (выбирает контроллер) | — |
| kubeconform | v0.8.0, образ `ghcr.io/yannh/kubeconform` | команда ниже |

## Запуск

Из корня репозитория:

```bash
./scripts/kind-up.sh        # кластер freelance, Envoy Gateway, сборка и загрузка образов ser-*:latest
./scripts/init-k8s-env.sh   # секреты: k8s/overlays/local/app.env и db.env
./scripts/k8s-deploy.sh     # манифесты, миграции, тестовые пользователи, ожидание готовности
open http://127.0.0.1:8080
```

С нуля на Docker Desktop (4 ГБ, 8 CPU) `kind-up.sh` занимает ~1,5 минуты (дольше при первом скачивании образов), `k8s-deploy.sh` — 60–85 с. Каждый скрипт завершается с кодом ≠ 0 при любом сбое.

**`scripts/kind-up.sh`** создаёт кластер `freelance` по [kind-config.yaml](kind-config.yaml) (один узел, контекст kubectl — `kind-freelance`). Затем ставит Envoy Gateway v1.9.2 (`kubectl apply --server-side`; в `install.yaml` есть CRD Gateway API, CRD Envoy Gateway и контроллер в namespace `envoy-gateway-system`) и ждёт `Available` контроллера. После этого собирает пять образов (`ser-auth`, `ser-task`, `ser-time`, `ser-gateway`, `ser-frontend`) через `docker compose build` и загружает их в узел (`kind load docker-image`). Секреты и `.env` ему не нужны. Повторный запуск кластер не пересоздаёт, Envoy Gateway применяет без изменений, образы пересобирает и загружает заново. После изменения кода запустите `kind-up.sh`, затем `k8s-deploy.sh` и `rollout restart` изменённых Deployment (см. «Известные ограничения»).

**`scripts/init-k8s-env.sh`** создаёт `k8s/overlays/local/app.env` (`SECRET_KEY`) и `db.env` (три пароля баз) по шаблонам [app.env.example](overlays/local/app.env.example) и [db.env.example](overlays/local/db.env.example) со случайными значениями, права 600. Повторный запуск дописывает только отсутствующие или пустые ключи, значения не печатает. Если сгенерировать значение не удалось (нет python3 и openssl), скрипт печатает ошибку и завершается с кодом 1, пустых значений в файлах нет; после установки python3 или openssl повторный запуск допишет недостающее. Файлы в `.gitignore`, с корневым `.env` compose они не связаны.

**`scripts/k8s-deploy.sh`** — аналог `docker compose up --wait`. Работает только с контекстом `kind-freelance` и сначала проверяет, что в кластере есть Envoy Gateway, а в overlay — файлы секретов. Порядок:
1. удаляет старые Job миграций и seed (по метке `app.kubernetes.io/component`);
2. `kubectl apply -k k8s/overlays/local`;
3. ждёт Job `auth-migrate`, `task-migrate`, `time-migrate` (`alembic upgrade head`); при `Failed` печатает лог Job и выходит;
4. применяет `k8s/overlays/local-seed` и ждёт Job `auth-seed` (тестовые пользователи);
5. ждёт `rollout status` баз и сервисов;
6. ждёт `Programmed` у Gateway `entry`: Envoy получил маршруты, вход работает.

Повторный запуск безопасен: миграции и seed идемпотентны, пользователи не дублируются.

## Адрес и пользователи

Приложение — `http://127.0.0.1:8080`, API — `http://127.0.0.1:8080/api` (тот же адрес, `/api` уходит в API Gateway приложения). Порт открыт только на `127.0.0.1`.

Тестовых пользователей создаёт Job `auth-seed`. Он есть только в локальном overlay `local-seed`, в base его нет:

| Email | Пароль | Роль |
|---|---|---|
| admin@example.com | password123 | admin |
| user1@example.com | password123 | user |
| user2@example.com | password123 | user |

```bash
curl -m 15 -X POST http://127.0.0.1:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password123"}'
```

Вход занимает около 2,5 с (см. «Известные ограничения»).

## Как устроено

### Каталоги

```
k8s/
├── base/                 манифесты без локальных допущений
│   ├── namespace.yaml    freelance-service, метки Pod Security Admission
│   ├── configmap.yaml    service-config: адреса сервисов, ALGORITHM, CORS_ORIGINS, GATEWAY_URL фронта
│   ├── pvc.yaml          тома трёх баз
│   ├── databases.yaml    auth-db, task-db, time-db (StatefulSet, postgres:15-alpine)
│   ├── migrations.yaml   Job auth-migrate, task-migrate, time-migrate
│   ├── services.yaml     ser-auth, ser-task, ser-time
│   ├── gateway-frontend.yaml  ser-gateway (API Gateway приложения), ser-frontend (nginx)
│   ├── entrypoint.yaml   вход: Gateway entry + HTTPRoute entry-routes
│   └── network-policy.yaml    default deny и разрешённые связи
├── overlays/local/       kind: Secret'ы из app.env и db.env, imagePullPolicy: Never,
│                         GatewayClass + EnvoyProxy (NodePort 30080), вход от Envoy в NetworkPolicy
├── overlays/local-seed/  overlay local + Job auth-seed и его сетевая политика
└── kind-config.yaml      кластер kind (не манифест Kubernetes)
```

### Вход

```
Браузер → 127.0.0.1:8080 → NodePort 30080 → Envoy (Gateway "entry", HTTPRoute "entry-routes")
                              /api/*  → ser-gateway:8000 → ser-auth, ser-task, ser-time
                              /*      → ser-frontend:8080 (статика; его /api/ тоже идёт на ser-gateway)
```

В base ([entrypoint.yaml](base/entrypoint.yaml)) описаны `Gateway` `entry` (listener HTTP :80) и маршруты: `PathPrefix /api` → `ser-gateway:8000`, `PathPrefix /` → `ser-frontend:8080`. В base класс Gateway только назван (`freelance`), а его реализацию задаёт overlay ([gatewayclass.yaml](overlays/local/gatewayclass.yaml)): `GatewayClass` контроллера Envoy Gateway и `EnvoyProxy`, у которого сервис Envoy — `NodePort` 30080. Этот порт узла `kind-config.yaml` пробрасывает на `127.0.0.1:8080`. Под и Service Envoy контроллер создаёт в `envoy-gateway-system`. В `freelance-service` все сервисы `ClusterIP`, `LoadBalancer` и `NodePort` нет.

Envoy нормализует путь до маршрутизации (`/api/tasks/../auth/me` → `/api/auth/me`), поэтому маршрут и авторизация gateway видят один и тот же путь. `GET /health` через вход отдаёт фронт (маршрут `/`), здоровье `ser-gateway` видно по его probes.

### Конфигурация и секреты

- Несекретное — ConfigMap `service-config` ([configmap.yaml](base/configmap.yaml)): адреса сервисов, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `CORS_ORIGINS` (`http://localhost:8080,http://127.0.0.1:8080`), `GATEWAY_URL` фронта. `GATEWAY_URL` задан полным именем (`ser-gateway.freelance-service.svc.cluster.local`): `resolver` nginx не применяет search-домены, с коротким `ser-gateway` фронт отвечает 502. ConfigMap без хеша в имени, поэтому после его правки нужен `kubectl rollout restart` соответствующего Deployment.
- Секреты собирает `secretGenerator` в [overlays/local](overlays/local/kustomization.yaml): `app-secrets` (`SECRET_KEY`) из `app.env`, `db-credentials` (три пароля) из `db.env`. Имена Secret'ов получают хеш содержимого, поэтому при смене секрета перезапускаются только поды, которые на него ссылаются (смена `SECRET_KEY` базы не трогает). Без файлов `kubectl kustomize` падает с `no such file or directory`.
- `DATABASE_URL` собирается в манифесте: `DB_PASSWORD` из Secret, затем `postgresql+psycopg://<svc>_user:$(DB_PASSWORD)@<svc>-db:5432/<svc>_db`. Пароли только `[A-Za-z0-9_-]`.
- Пароль БД применяется при создании тома. После смены пароля удалите namespace вместе с томами (`kubectl --context kind-freelance delete namespace freelance-service`) и запустите `k8s-deploy.sh`.

### Миграции и seed

Схему создают Job `*-migrate` ([migrations.yaml](base/migrations.yaml)), по одному поду на деплой, а не реплики сервисов. Seed — отдельный overlay [local-seed](overlays/local-seed): в одном `apply` порядка нет, и seed стартовал бы раньше миграций. Каталог соседний, а не `local/seed`: kustomize запрещает подкаталогу ссылаться на родителя. На чистом кластере первая попытка Job миграций обычно падает (`failed to resolve host 'auth-db'`: под базы ещё не готов), Job повторяет сам (`backoffLimit: 6`).

### Реплики

У `ser-auth`, `ser-task`, `ser-time`, `ser-gateway`, `ser-frontend` по две реплики, у баз (StatefulSet) — одна. Состояния в памяти процесса у сервисов нет (refresh-токен — JWT), запрос может обслужить любая реплика. Обновление — rolling update по умолчанию: новый под становится `Ready` до остановки старого.

### Безопасность подов

На namespace включён Pod Security Admission `restricted` ([namespace.yaml](base/namespace.yaml)): `enforce` закреплён на версии правил `v1.35`, `warn` и `audit` идут по `latest`. У всех подов, Job и баз:
- `runAsNonRoot: true`, `runAsUser` 10001 (Python-сервисы, в образе `USER 10001`), 101 (nginx фронта), 70 (postgres);
- `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`;
- `readOnlyRootFilesystem: true`. Python-сервисы на диск не пишут. nginx пишет в `emptyDir` `/tmp` и `/etc/nginx/conf.d`, postgres — в том данных и в `emptyDir` `/var/run/postgresql` и `/tmp`;
- `automountServiceAccountToken: false`.

Postgres дополнительно получает `fsGroup: 70`. На томе `local-path` kind он не применяется, но каталог тома создаётся с правами `0777`. В логе базы при старте есть безвредное `chmod: /var/run/postgresql: Operation not permitted`.

### Probes

У приложений `startupProbe` `GET /`: раз в 2 с, до 30 попыток (до 60 с на холодный старт). После первого ответа включаются `livenessProbe` (каждые 10 с) и `readinessProbe` (каждые 5 с). У баз — `pg_isready -U … -d …`.

### Сетевые политики

По умолчанию запрещено всё (`default-deny-all`: вход и выход каждому поду). Разрешено (порты — порты контейнеров):
- DNS: все поды → kube-dns в `kube-system`, UDP и TCP 53;
- вход: поды прокси Envoy нашего Gateway (`envoy-gateway-system`) → `ser-frontend:8080` и `ser-gateway:8000` ([overlays/local/network-policy-entry.yaml](overlays/local/network-policy-entry.yaml));
- `ser-frontend` → `ser-gateway:8000`; `ser-gateway` → `ser-auth:8001`, `ser-task:8002`, `ser-time:8003`; `ser-task` → `ser-time:8003`;
- каждый сервис и его Job миграций → своя база `:5432`; `auth-seed` → `auth-db:5432` ([overlays/local-seed/network-policy-seed.yaml](overlays/local-seed/network-policy-seed.yaml)).

Остальное запрещено: сервис не достанет до чужой базы, фронт — до сервисов в обход gateway, поды — до интернета. Запрещённое соединение не отвергается, а обрывается по таймауту. Поэтому ошибка в политике выглядит как зависание, а не как `connection refused`. Одна политика описывает один под (что он принимает и куда ходит), так что у каждой связи две стороны. Пробы kubelet kindnet не ограничивает.

## Диагностика

Удобно завести функцию (в zsh переменная с командой не разбивается на слова):

```bash
k() { kubectl --context kind-freelance -n freelance-service "$@"; }
```

Состояние:

```bash
k get pods -o wide                       # 10 подов приложений + 3 базы Running, 0 RESTARTS
k get jobs                               # auth-migrate, task-migrate, time-migrate, auth-seed — Complete
k get gateway,httproute                  # entry PROGRAMMED True
k get networkpolicy                      # 17 политик, POD-SELECTOR — кого касается
kubectl --context kind-freelance -n envoy-gateway-system get pods,svc   # контроллер и прокси, NodePort 80:30080
```

Логи:

```bash
k logs deploy/ser-gateway                # один под Deployment
k logs -l app=ser-auth --prefix          # все реплики
k logs job/auth-migrate                  # task-migrate, time-migrate, auth-seed
k logs <под> --previous                  # предыдущий контейнер, если под перезапускался
kubectl --context kind-freelance -n envoy-gateway-system logs deploy/envoy-gateway   # контроллер входа
```

В логах `ser-auth` и `auth-seed` есть известный шум: `(trapped) error reading bcrypt version` с traceback (passlib и bcrypt 4, на работу не влияет). У Job миграций на чистом кластере в упавших первых попытках — `Name or service not known` (см. «Миграции и seed»).

События и причины:

```bash
k get events --sort-by=.lastTimestamp    # Unhealthy (probes), FailedScheduling, BackOff и т. п.
k describe pod <под>                     # статус контейнеров, причина перезапуска, события пода
k describe job auth-migrate
k describe gateway entry                 # условия Accepted / Programmed и их причины
k describe networkpolicy ser-task
```

Сквозной прогон: `SMOKE_MODE=k8s bash tests/smoke.sh` — 114 проверок через `http://127.0.0.1:8080`. `/health` через вход отдаёт фронт, поэтому smoke проверяет его изнутри пода `ser-gateway` (тело: `upstreams.auth/task/time` все `true`).

Статическая проверка — на выводе kustomize, а не на каталоге `k8s/` (там лежит `kind-config.yaml`, не манифест). kubeconform не знает схем CRD, поэтому четыре ресурса входа пропускаются явно, а проверяет их API-сервер:

```bash
kubectl kustomize k8s/overlays/local | docker run --rm -i ghcr.io/yannh/kubeconform:v0.8.0 \
  -strict -summary -skip Gateway,GatewayClass,HTTPRoute,EnvoyProxy -     # 41 valid + 4 skipped (local-seed: 44 + 4)
kubectl kustomize k8s/overlays/local | kubectl --context kind-freelance apply --dry-run=server -f -
```

Вывод `kubectl kustomize` содержит Secret'ы (base64), в файлы и логи его не сохраняйте. Шум, который не означает ошибку: `httproute … configured` при каждом `apply` (у CRD нет strategic merge, объект не меняется), `namespace: freelance-service` у кластерного `GatewayClass` в выводе kustomize (kubectl это поле отбрасывает).

## Удаление

```bash
kubectl --context kind-freelance delete namespace freelance-service   # приложение и данные баз (PVC), кластер остаётся
kind delete cluster --name freelance                                  # весь кластер вместе с Envoy Gateway и образами в узле
```

Файлы секретов `k8s/overlays/local/app.env` и `db.env` при этом остаются. Чтобы сгенерировать новые, удалите их и запустите `./scripts/init-k8s-env.sh`. Если namespace уже был, удалите его: пароль БД применяется только при создании тома.

## kind в CI

Job `kind` в [.github/workflows/ci.yml](../.github/workflows/ci.yml) (раздел «CI» корневого README) на каждом прогоне поднимает кластер с нуля на раннере `ubuntu-24.04` теми же скриптами, что и локально:

1. kubectl v1.35.9 скачивается с `dl.k8s.io` со сверкой sha256, закреплённой в workflow. Свой kubectl раннера (1.37) к серверу 1.35 не подходит: разница больше одной минорной версии. kind берётся с раннера, но его версия должна быть v0.33.0, иначе job падает;
2. `./scripts/kind-up.sh` — кластер, Envoy Gateway (sha256 `install.yaml`), сборка и загрузка образов;
3. `./scripts/init-k8s-env.sh` — новые секреты; workflow сразу маскирует их значения и base64 (`::add-mask::`);
4. `./scripts/k8s-deploy.sh`, затем `SMOKE_MODE=k8s bash tests/smoke.sh` (114) и e2e через вход `http://127.0.0.1:8080` (на Linux `run.sh` работает с `--network host`);
5. `kubectl kustomize … | kubectl apply --dry-run=server -f -` для `local` и `local-seed`: в лог попадают только строки `unchanged` / `configured`, содержимое манифестов — нет.

Если что-то упало, шаг «диагностика» печатает `get pods,jobs -o wide`, события, `describe gateway entry`, поды и логи контроллера Envoy Gateway, логи подов приложения (`--all-containers`, хвост, и `--previous`, если контейнер перезапускался). Скриншоты и trace e2e — артефакт `e2e-kind`. Кластер каждый раз новый, поэтому ограничение «`k8s-deploy.sh` не перекатывает поды при новом образе с тем же тегом» (см. ниже) в CI не мешает.

Скрипты в CI запускаются без изменений. В шаге 1.5.7 в них поправлено только то, на что указал shellcheck, поведение прежнее (проверено на копиях в macOS bash 3.2 и Linux bash 5.2): в `init-env.sh` и `init-k8s-env.sh` цикл по ключам шаблона — `while read` из подстановки процесса вместо `for key in $(grep …)`; в `k8s-deploy.sh` проверка Envoy Gateway — `if ! … || ! …; then die` вместо `A && B || die`.

## Известные ограничения

- **Один узел.** Реплики живут на одном узле kind, PodDisruptionBudget, anti-affinity и HPA не настроены (metrics-server нет). Отказ узла — отказ всего приложения.
- **502/503 при rollout.** `kubectl rollout restart` под непрерывной нагрузкой даёт единичные ошибки в момент остановки старого пода: фронт и gateway — 503, task — 502. Envoy ещё шлёт запросы на под, который уже получил SIGTERM. Нет `preStop` и плавного завершения, план — этап 1.6.
- **Вход занимает ~2,5 с.** bcrypt при лимите CPU 200m у `ser-auth`. Для `curl` к `/api/auth/login` ставьте таймаут от 15 с (`-m 15`).
- **Probes чувствительны к нагрузке на CPU хоста.** У liveness и readiness таймаут по умолчанию 1 с. Пока рядом с кластером шли `docker compose up --build` и старт compose (около двух минут), пробы всех сервисов и баз получали таймауты, а один под `ser-task` был перезапущен по liveness (завершился штатно, ошибок нет). На время сборки compose кластер лучше не нагружать проверками. Решать вместе с `/ready` (этап 1.6).
- **Readiness не проверяет БД.** Probes идут на публичный `GET /`: под готов, даже если база недоступна. Кроме того, сервисы стартуют параллельно с Job миграций и могут стать `Ready` до появления таблиц: на чистом кластере в первые ~30 с запросы к API могут получить 500. `k8s-deploy.sh` завершается только после миграций, поэтому после него окна нет. `/ready` с проверкой БД и ревизии схемы — этап 1.6.
- **Job неизменяемы, деплоить только через `k8s-deploy.sh`.** Голый `kubectl apply -k` поверх существующих Job падает на изменённом Job (`spec.template: … field is immutable`), а неизменённый не перезапускает. Тогда миграции из нового образа не выполнятся.
- **Gateway дважды не стал `Programmed`.** При `k8s-deploy.sh` поверх уже работающего namespace скрипт два раза упал на ожидании `Programmed` у Gateway: `NoResources: Envoy replicas unavailable` (шаг 1.4.8) и `AddressNotAssigned` (1.5.2), оба раза при здоровом Envoy. На чистом деплое и на повторе не воспроизводилось. Если повторится, сохраните `k describe gateway entry` и логи `envoy-gateway` (в CI их печатает шаг «диагностика»), затем удалите namespace и задеплойте заново.
- **`k8s-deploy.sh` не перекатывает поды при новом образе с тем же тегом.** Манифесты ссылаются на `ser-*:latest` с `imagePullPolicy: Never`. `kind-up.sh` загружает в узел новый образ, но спецификация Deployment не меняется, и после деплоя работают старые поды. Локально после правок кода нужен `k rollout restart deployment` (найдено в 1.5.4).
- **Образы `:latest` и `imagePullPolicy: Never`.** Образы есть только в узле kind (`kind load`), реестра нет. Облачный overlay (реестр и теги по коммиту, TLS, управляемый Postgres, внешнее хранилище секретов) — будущий этап.
