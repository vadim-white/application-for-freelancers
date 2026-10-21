# Kubernetes: локальный кластер kind

Инструкция по запуску приложения в Kubernetes. Кластер — [kind](https://kind.sigs.k8s.io/) (Kubernetes в Docker), один узел на этой машине. Манифесты собирает kustomize (встроен в kubectl), вход — Gateway API с контроллером [Envoy Gateway](https://gateway.envoyproxy.io/). Облачного варианта (реестр образов, TLS, управляемый Postgres) пока нет: [base](base) написана без локальных допущений, но overlay есть только для kind.

Docker Compose и кластер независимы: у них разные порты (compose — `127.0.0.1:5173` и `:8000`, кластер — `127.0.0.1:8080`) и разные секреты. Оба стека помещаются в 4 ГБ и могут работать одновременно. Сборка compose рядом с работающим кластером отнимает у него CPU: вход замедляется (медиана 0,45 с, до 1,5 с), но пробы не падают и поды не перезапускаются (проверено сборкой `docker compose build --no-cache` и `up --wait`, см. «Ресурсы»).

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
./scripts/kind-up.sh        # кластер freelance, Envoy Gateway, сборка и загрузка образов ser-*:<SHA коммита>
./scripts/init-k8s-env.sh   # секреты: k8s/overlays/local/app.env и db.env
./scripts/k8s-deploy.sh     # манифесты, миграции, тестовые пользователи, ожидание готовности
open http://127.0.0.1:8080
```

С нуля на Docker Desktop (4 ГБ, 8 CPU) `kind-up.sh` занимает ~1,5 минуты (дольше при первом скачивании образов), `k8s-deploy.sh` — 60–85 с. Каждый скрипт завершается с кодом ≠ 0 при любом сбое.

**`scripts/kind-up.sh`** создаёт кластер `freelance` по [kind-config.yaml](kind-config.yaml) (один узел, контекст kubectl — `kind-freelance`). Затем ставит Envoy Gateway v1.9.2 (`kubectl apply --server-side`; в `install.yaml` есть CRD Gateway API, CRD Envoy Gateway и контроллер в namespace `envoy-gateway-system`) и ждёт `Available` контроллера. После этого собирает пять образов (`ser-auth`, `ser-task`, `ser-time`, `ser-gateway`, `ser-frontend`) через `docker compose build` и загружает их в узел (`kind load docker-image`) с тегом по коммиту: `git rev-parse --short=12 HEAD`, а при незакоммиченных правках (`git status --porcelain` не пуст) — `<sha>-dirty-<ГГГГММДДччммсс>`. Тег записывается в `k8s/overlays/local/image-tag` (в `.gitignore`), его читает `k8s-deploy.sh`. Compose тег не касается: образы на хосте остаются `ser-*:latest`, тег по коммиту ставится только на время `kind load`. В конце скрипт чистит узел: снимает старые теги `ser-*`, кроме текущего и тех, на которых работают поды, и удаляет ссылки, которые держат содержимое снятых образов (подробнее — «Образы и теги»). Секреты и `.env` ему не нужны. Повторный запуск кластер не пересоздаёт, Envoy Gateway применяет без изменений, образы пересобирает и загружает заново. После изменения кода достаточно `kind-up.sh` и `k8s-deploy.sh`: новый тег меняет спецификацию подов, и Deployment перекатываются сами.

**`scripts/init-k8s-env.sh`** создаёт `k8s/overlays/local/app.env` (`SECRET_KEY`) и `db.env` (три пароля баз) по шаблонам [app.env.example](overlays/local/app.env.example) и [db.env.example](overlays/local/db.env.example) со случайными значениями, права 600. Повторный запуск дописывает только отсутствующие или пустые ключи, значения не печатает. Если сгенерировать значение не удалось (нет python3 и openssl), скрипт печатает ошибку и завершается с кодом 1, пустых значений в файлах нет; после установки python3 или openssl повторный запуск допишет недостающее. Файлы в `.gitignore`, с корневым `.env` compose они не связаны.

**`scripts/k8s-deploy.sh`** — аналог `docker compose up --wait`. Работает только с контекстом `kind-freelance` и сначала проверяет, что в кластере есть Envoy Gateway, в overlay — файлы секретов и `image-tag`, а в узле — пять образов с этим тегом (иначе просит запустить `kind-up.sh`). Затем генерирует в `k8s/overlays/.deploy/` (в `.gitignore`) две kustomization: `app` (ресурс `../../local`) и `seed` (`../../local-seed`) с одинаковым блоком `images:` (`newTag` — тег из `image-tag`). Overlay `local` и `local-seed` в git остаются на `:latest`. Порядок:
1. удаляет старые Job миграций и seed (по метке `app.kubernetes.io/component`);
2. `kubectl apply -k k8s/overlays/.deploy/app`;
3. ждёт Job `auth-migrate`, `task-migrate`, `time-migrate` (`alembic upgrade head`); при `Failed` печатает лог Job и выходит;
4. применяет `k8s/overlays/.deploy/seed` и ждёт Job `auth-seed` (тестовые пользователи);
5. ждёт `rollout status` баз и сервисов;
6. ждёт `Programmed` у Gateway `entry`: Envoy получил маршруты, вход работает.

Повторный запуск безопасен: миграции и seed идемпотентны, пользователи не дублируются. Без пересборки тег тот же, Deployment `unchanged`, поды не перекатываются.

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

Вход занимает 0,25–0,3 с (bcrypt; у `ser-auth` нет лимита CPU, см. «Ресурсы»).

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
│                         (+ image-tag от kind-up.sh, не в git)
├── overlays/local-seed/  overlay local + Job auth-seed и его сетевая политика
├── overlays/.deploy/     app и seed: те же overlay с тегом образов (генерирует k8s-deploy.sh, не в git)
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

### Образы и теги

Реестра нет: образы `ser-*` есть только в узле kind (`kind load`), поэтому у Deployment и Job `imagePullPolicy: Never` (патч в `overlays/local`, у `auth-seed` — в самом манифесте). В `base` образы записаны как `ser-*:latest`, реальный тег подставляет `k8s-deploy.sh` через `images:` в сгенерированных kustomization. Тег — SHA коммита: при новом коммите или сборке с правками меняется спецификация подов, и rolling update идёт сам; с одним тегом `:latest` Deployment не менялся, и после деплоя работали старые поды. Сборка с незакоммиченными правками каждый раз получает новый тег (время в `-dirty-…`) и перекатывает все пять Deployment, даже если менялся один сервис. В CI checkout чистый, тег всегда без `-dirty`.

Чистка узла в `kind-up.sh` идёт через `ctr` (containerd), а не `crictl rmi`: `crictl rmi` снимает все теги с тем же ID образа, то есть и текущий, если образ между сборками не менялся (проверено). Снимаются старые теги `ser-*`, кроме текущего и тех, что в спецификации подов. Ещё удаляются ссылки `import-<дата>@sha256:…`, которые оставляет каждый `kind load`, и служебные ссылки CRI `sha256:<ID>` у образов без имени: пока они есть, содержимое старых образов остаётся на диске узла. `crictl rmi` их не находит (имя `import-…` хранится без префикса `docker.io/library/`). После такой чистки `crictl images` до перезапуска узла может показывать строки `import-… <none>` уже удалённых образов: это кэш CRI, в containerd ссылок нет, после `docker start` узла строки пропадают.

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

| Проба | Сервисы auth, task, time | Gateway | Фронт | Базы |
|---|---|---|---|---|
| startup | `GET /`, раз в 2 с, до 30 попыток (60 с на холодный старт) | так же | так же | — |
| liveness | `GET /`, каждые 10 с, таймаут 3 с, 6 неудач | так же | так же | `pg_isready`, таймаут 3 с |
| readiness | `GET /ready`, каждые 5 с, таймаут 3 с, 3 неудачи | `GET /ready` (без проверки сервисов) | `GET /` | `pg_isready`, таймаут 3 с |

Liveness и readiness включаются после первого ответа startup. Liveness проверяет только, что процесс отвечает (`GET /` базу не трогает): перезапуск не чинит недоступную базу. Перезапуск по liveness — через 60 с неудач (6 × 10 с): он дороже снятия с трафика. Таймаут проб 3 с вместо 1 с по умолчанию: под нагрузкой узла ответ дольше 1 с — ещё не зависание.

`/ready` у auth, task, time (вне `/api`, через gateway и вход недоступен):
- `SELECT 1`, затем ревизия из `alembic_version` сравнивается с head миграций из образа (`ScriptDirectory`, head и его предки читаются при старте);
- таблицы нет, она пустая или ревизия — предок head (схема старше кода) → 503 `{"ready": false, "reason": …}`; ошибка соединения → 503 `database unavailable` (текст ошибки драйвера — только в логе пода, строка `not ready: …`);
- ревизия равна head или незнакома → 200. Незнакомая считается более новой: при expand/contract миграция применяется до выката кода, и старые поды при rolling update не должны выпадать из балансировки (простое «ревизия == head» сняло бы их все);
- соединение к PostgreSQL — с `connect_timeout` 2 с, меньше таймаута пробы.

Что это даёт:
- **Окно «Ready до миграций» закрыто.** Сервисы стартуют параллельно с Job миграций, но остаются `0/1`, пока схемы нет (события `Readiness probe failed: HTTP probe failed with statuscode: 503`). На чистом кластере (`delete namespace` → `k8s-deploy.sh`) поды `ser-task` были не готовы ~25 с и стали `Ready` сразу после Job `task-migrate`.
- **Недоступная база снимает сервис с трафика, но не перезапускает его.** `scale statefulset task-db --replicas=0`: через ~10 с оба пода `ser-task` `0/1`, за 75 с без базы — 0 перезапусков; после возврата базы `Ready` через 3–6 с. Пока ни одного готового пода нет, запросы к этому сервису через gateway получают 504 через 5 с (Service без готовых endpoint'ов не отклоняет соединение, срабатывает connect-таймаут gateway); остальные сервисы работают.
- `/ready` gateway не проверяет сервисы: иначе один упавший сервис снимал бы с трафика весь gateway и вместе с ним пути к остальным. Доступность сервисов — в `/health` (тело `upstreams`).

Проверить вручную (изнутри gateway, как smoke):

```bash
k exec deploy/ser-gateway -- python -c "import urllib.request as u;print(u.urlopen('http://ser-task:8002/ready').read().decode())"
```

### Ресурсы

| | requests CPU | limits CPU | requests / limits памяти |
|---|---|---|---|
| auth, task, time, gateway | 50m | нет | 128Mi / 256Mi |
| фронт | 25m | нет | 32Mi / 64Mi |
| базы | 100m | 500m | 256Mi / 512Mi |
| Job миграций и seed | 50m | 200m | 128Mi / 256Mi |

**Почему у приложений нет лимита CPU.** Лимит CPU — это квота CFS: исчерпав её за период 100 мс, процесс стоит до следующего периода, даже если узел простаивает. При лимите 200m bcrypt при входе растягивался до 1,7–2,6 с (на узле 8 CPU, без нагрузки), а пробы с таймаутом 1 с падали, пока рядом собирался compose (1.4.9: таймауты у всех сервисов и перезапуск `ser-task`). Без лимита под берёт свободный CPU узла, а при конкуренции делит его пропорционально requests. Вход стал 0,25–0,3 с; сборка compose `--no-cache` рядом с кластером — 0 неудачных проб и 0 перезапусков, вход за это время 0,29–1,48 с. Лимит памяти остаётся: память не сжимается, без лимита утечка одного пода вытеснила бы остальные (с лимитом — OOMKill только этого пода). У баз лимит CPU 500m остаётся: в замере троттлинг баз единичный (`nr_throttled` 0–1). У Job миграций и seed лимит 200m тоже остаётся: они короткие и трафик не обслуживают.

**Requests — по замеру** (`kubectl top` нет, metrics-server не установлен; замер — `cpu.stat` cgroup подов в узле): в простое сервисы тратят 6–11m (в основном пробы `/ready` с запросом к базе), фронт меньше 1m; во время smoke task и time — 13–22m, auth — 130–140m (один вход — ~0,26 с CPU). 50m покрывают устойчивую нагрузку с запасом, всплески bcrypt забирают свободный CPU узла. Сумма requests на узле — 23 % от 8 CPU.

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
k get deploy -o wide                     # IMAGES — тег образов (SHA коммита)
k get jobs                               # auth-migrate, task-migrate, time-migrate, auth-seed — Complete
k get gateway,httproute                  # entry PROGRAMMED True
k get networkpolicy                      # 17 политик, POD-SELECTOR — кого касается
kubectl --context kind-freelance -n envoy-gateway-system get pods,svc   # контроллер и прокси, NodePort 80:30080
cat k8s/overlays/local/image-tag                                         # тег последней сборки kind-up.sh
docker exec freelance-control-plane crictl images | grep ser-            # образы в узле: текущий тег и теги работающих подов
```

Логи:

```bash
k logs deploy/ser-gateway                # один под Deployment
k logs -l app=ser-auth --prefix          # все реплики
k logs job/auth-migrate                  # task-migrate, time-migrate, auth-seed
k logs <под> --previous                  # предыдущий контейнер, если под перезапускался
kubectl --context kind-freelance -n envoy-gateway-system logs deploy/envoy-gateway   # контроллер входа
```

У Job миграций на чистом кластере в упавших первых попытках — `Name or service not known` (см. «Миграции и seed»).

События и причины:

```bash
k get events --sort-by=.lastTimestamp    # Unhealthy (probes), FailedScheduling, BackOff и т. п.
k describe pod <под>                     # статус контейнеров, причина перезапуска, события пода
k describe job auth-migrate
k describe gateway entry                 # условия Accepted / Programmed и их причины
k describe networkpolicy ser-task
```

Сквозной прогон: `SMOKE_MODE=k8s bash tests/smoke.sh` — 118 проверок через `http://127.0.0.1:8080`. `/health` через вход отдаёт фронт, поэтому smoke проверяет его изнутри пода `ser-gateway` (тело: `upstreams.auth/task/time` все `true`), там же — `/ready` трёх сервисов.

Статическая проверка — на выводе kustomize, а не на каталоге `k8s/` (там лежит `kind-config.yaml`, не манифест). kubeconform не знает схем CRD, поэтому четыре ресурса входа пропускаются явно, а проверяет их API-сервер:

```bash
kubectl kustomize k8s/overlays/local | docker run --rm -i ghcr.io/yannh/kubeconform:v0.8.0 \
  -strict -summary -skip Gateway,GatewayClass,HTTPRoute,EnvoyProxy -     # 41 valid + 4 skipped (local-seed: 44 + 4)
kubectl kustomize k8s/overlays/.deploy/app | kubectl --context kind-freelance apply --dry-run=server -f -   # и .deploy/seed
```

kubeconform можно запускать на overlay из git (`:latest`), а `apply --dry-run=server` — только на `.deploy/app` и `.deploy/seed` (их пишет `k8s-deploy.sh` с тегом из `image-tag`). У развёрнутых Job шаблон пода неизменяем, и overlay с другим тегом образа сервер отклоняет: `Job.batch "auth-migrate" is invalid: spec.template: … field is immutable`.

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
2. `./scripts/kind-up.sh` — кластер, Envoy Gateway (sha256 `install.yaml`), сборка и загрузка образов; checkout чистый, поэтому тег — SHA коммита без `-dirty`;
3. `./scripts/init-k8s-env.sh` — новые секреты; workflow сразу маскирует их значения и base64 (`::add-mask::`);
4. `./scripts/k8s-deploy.sh`, затем `SMOKE_MODE=k8s bash tests/smoke.sh` (118) и e2e через вход `http://127.0.0.1:8080` (на Linux `run.sh` работает с `--network host`);
5. `kubectl kustomize … | kubectl apply --dry-run=server -f -` для `.deploy/app` и `.deploy/seed` (overlay `local` и `local-seed` с тем тегом, что развёрнут): в лог попадают только строки `unchanged` / `configured`, содержимое манифестов — нет.

Если что-то упало, шаг «диагностика» печатает `get pods,jobs -o wide`, `get deploy -o wide` (виден тег образов), события, `describe gateway entry`, поды и логи контроллера Envoy Gateway, логи подов приложения (`--all-containers`, хвост, и `--previous`, если контейнер перезапускался). Скриншоты и trace e2e — артефакт `e2e-kind`. Шаг 5 проверяет те же манифесты, что применил `k8s-deploy.sh`: с overlay из git (`:latest`) Job миграций дают `field is immutable`, а Deployment — `configured` вместо `unchanged`.

Скрипты в CI запускаются без изменений. В шаге 1.5.7 в них поправлено только то, на что указал shellcheck, поведение прежнее (проверено на копиях в macOS bash 3.2 и Linux bash 5.2): в `init-env.sh` и `init-k8s-env.sh` цикл по ключам шаблона — `while read` из подстановки процесса вместо `for key in $(grep …)`; в `k8s-deploy.sh` проверка Envoy Gateway — `if ! … || ! …; then die` вместо `A && B || die`.

## Известные ограничения

- **Один узел.** Реплики живут на одном узле kind, PodDisruptionBudget, anti-affinity и HPA не настроены (metrics-server нет). Отказ узла — отказ всего приложения.
- **502/503 при rollout.** `kubectl rollout restart` под непрерывной нагрузкой даёт единичные ошибки в момент остановки старого пода: фронт и gateway — 503, task — 502. Envoy ещё шлёт запросы на под, который уже получил SIGTERM. Нет `preStop` и плавного завершения, план — этап 1.6. `k8s-deploy.sh` после новой сборки сам перекатывает все Deployment, поэтому то же окно бывает сразу после деплоя: smoke, запущенный через ~1 мин после перекатки, однажды получил 502 на логине (gateway не достучался до `ser-auth`), и проверки с этим токеном упали.
- **Ревизия из чужой ветки считается новее.** `/ready` отличает только «предок head» (503) от «не предок» (200). Если база окажется на ревизии, которой нет в цепочке образа, по ошибке деплоя (миграция из другой ветки), под будет `Ready`. Это осознанный компромисс ради expand/contract: отличить «новее» от «чужой» без истории ревизий в образе нельзя.
- **Зависшая база на открытом соединении.** `connect_timeout` (2 с) действует только на новые соединения. Если база перестала отвечать, а соединение в пуле ещё открыто (проверено в compose `docker pause` базы), `SELECT 1` в `/ready` ждёт без ограничения: проба падает по своему таймауту (3 с), под снимается с трафика, но поток с запросом висит, пока база не ответит. Таких потоков не больше, чем соединений в пуле; запросы API на таких соединениях висят так же. `statement_timeout` и TCP keepalive не настроены.
- **Job неизменяемы, деплоить только через `k8s-deploy.sh`.** Голый `kubectl apply -k` поверх существующих Job падает на изменённом Job (`spec.template: … field is immutable`), а неизменённый не перезапускает. Тогда миграции из нового образа не выполнятся.
- **Gateway дважды не стал `Programmed`.** При `k8s-deploy.sh` поверх уже работающего namespace скрипт два раза упал на ожидании `Programmed` у Gateway: `NoResources: Envoy replicas unavailable` (шаг 1.4.8) и `AddressNotAssigned` (1.5.2), оба раза при здоровом Envoy. На чистом деплое и на повторе не воспроизводилось. Если повторится, сохраните `k describe gateway entry` и логи `envoy-gateway` (в CI их печатает шаг «диагностика»), затем удалите namespace и задеплойте заново.
- **Реестра нет, `imagePullPolicy: Never`.** Образы есть только в узле kind (`kind load`), теги по коммиту живут только там. Облачный overlay (реестр и публикация образов из CI с тем же SHA, TLS, управляемый Postgres, внешнее хранилище секретов) — будущий этап.
