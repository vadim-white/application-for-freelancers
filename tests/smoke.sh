#!/bin/bash
# Сквозной прогон (smoke) через gateway: tests/smoke.sh. Запуск: `bash tests/smoke.sh` из корня репозитория.
# Авторизация (из 1.1.6) и доступ «только свои» (1.2), записи времени, /health по телу, CORS.
# Идемпотентен: все объекты создаются в самом прогоне,
# проверки не опираются на данные прошлых запусков и проходят на чистой базе.
# Предшественник — docs/archive/smoke_1.2.9.sh (до 1.5.1, вне git).
#
# Два режима (SMOKE_MODE), seed-пользователи нужны в обоих:
#   compose (по умолчанию) — 116 проверок. Стек: `docker compose up --build -d --wait`
#     (сам скрипт готовности не ждёт: после --wait gateway слушает порт и логин seed-пользователей работает).
#   k8s — 114 проверок. Кластер kind: `./scripts/k8s-deploy.sh` (миграции, seed, вход Gateway).
#     Запросы идут через вход кластера http://127.0.0.1:8080 (Envoy Gateway, /api -> ser-gateway), как из
#     браузера; port-forward не нужен. Отличия от compose:
#     - нет четырёх проверок «localhost:8001/8002/8003/5432 closed»: кластер публикует на хост только порт
#       входа (8080), эти порты закрыты независимо от манифестов, проверка ничего не доказывает. Изоляцию
#       сервисов и баз внутри кластера (NetworkPolicy) smoke не проверяет: проверено вручную в шаге 1.4.7
#       (запрещённые связи — таймаут, ANALYSIS, раздел 13). Под политиками smoke проходит: его запросы идут
#       через вход, а «В обход gateway» — из пода ser-gateway к ser-task/ser-time/ser-auth (разрешено);
#       kubectl exec политиками не ограничивается (это не сетевой трафик пода);
#     - path traversal проверяется в два слоя (+2): через вход Envoy нормализует путь (RFC 3986) до gateway,
#       `../` и `%2e%2e` схлопываются в /api/auth/me — без токена 401, то есть авторизация не обойдена;
#       защита самого gateway (404) — запросом изнутри его пода, где путь приходит как есть.
#     GET / через вход отдаёт фронт (маршрут "/"), а не gateway; /health через вход тоже отдал бы фронт,
#     поэтому /health проверяется изнутри пода gateway (заодно подтверждает NetworkPolicy gateway -> сервисы).
# /health gateway всегда отвечает 200, доступность сервисов пишет только в теле (upstreams), поэтому
# проверяется тело: upstreams.auth, .task, .time все true (в обоих режимах).
# Переопределяется: SMOKE_G (адрес gateway или входа), SMOKE_ORIGIN (разрешённый CORS origin),
# KUBE_CONTEXT (kind-freelance).
MODE="${SMOKE_MODE:-compose}"
case "$MODE" in
  compose)
    G="${SMOKE_G:-http://localhost:8000}"
    CLOSED_PORTS="8001 8002 8003 5432"
    EXPECTED=116
    in_svc() { local s=$1; shift; docker exec "ser-$s" "$@"; }   # in_svc auth|gateway команда...
    in_auth_db() { docker exec ser-auth-db "$@"; }
    ;;
  k8s)
    KCTX="${KUBE_CONTEXT:-kind-freelance}"
    KNS=freelance-service
    G="${SMOKE_G:-http://127.0.0.1:8080}"
    CLOSED_PORTS=""
    EXPECTED=114
    in_svc() { local s=$1; shift; kubectl --context "$KCTX" -n "$KNS" exec "deploy/ser-$s" -- "$@"; }
    in_auth_db() { kubectl --context "$KCTX" -n "$KNS" exec auth-db-0 -c postgres -- "$@"; }
    ;;
  *) echo "SMOKE_MODE: compose или k8s, а не '$MODE'" >&2; exit 2 ;;
esac
# compose: дефолт CORS_ORIGINS gateway (localhost:5173); k8s: cors-origins из ConfigMap (адрес входа)
if [ "$MODE" = k8s ]; then ORIGIN="${SMOKE_ORIGIN:-http://127.0.0.1:8080}"; else ORIGIN="${SMOKE_ORIGIN:-http://localhost:5173}"; fi
echo "Режим $MODE, gateway $G, ожидается проверок: $EXPECTED"
PASS=0; FAIL=0
chk() { # name expected actual
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "OK   $1 ($3)"; else FAIL=$((FAIL+1)); echo "FAIL $1: expected $2, got $3"; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
J='Content-Type: application/json'
SFX="$(date +%s)$RANDOM"
jq_() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }
login() { curl -s $G/api/auth/login -H "$J" -d "{\"email\":\"$1\",\"password\":\"${2:-password123}\"}"; }
# req TOKEN METHOD PATH [JSON] -> http-код
req() {
  local a=(-s -o /dev/null -w '%{http_code}' -X "$2" "$G$3" -H "Authorization: Bearer $1" -H "$J")
  [ -n "${4:-}" ] && a+=(-d "$4")
  curl "${a[@]}"
}
# body TOKEN METHOD PATH [JSON] -> тело ответа
body() {
  local a=(-s -X "$2" "$G$3" -H "Authorization: Bearer $1" -H "$J")
  [ -n "${4:-}" ] && a+=(-d "$4")
  curl "${a[@]}"
}
ids() { jq_ '" ".join(str(x["id"]) for x in d)'; }       # список объектов -> "1 2 3"
has() { case " $1 " in *" $2 "*) echo 1;; *) echo 0;; esac; }  # has "1 2 3" 2 -> 1
# токен, подписанный ключом стека, с произвольными claims (python-jose внутри ser-auth)
forge() { # claims-json [key-expr]
  in_svc auth env CLAIMS="$1" KEY="${2:-}" python -c "
import os,time,json; from jose import jwt
c=json.loads(os.environ['CLAIMS']); now=int(time.time())
for k in ('exp','iat'):
    if k in c: c[k]=now+c[k]
print(jwt.encode(c, os.environ['KEY'] or os.environ['SECRET_KEY'], algorithm='HS256'))"; }

echo "== Публичные пути"
# /health по телу: "auth task time" для upstreams, равных true; пусто, если ответ не разобрался
health_up() { jq_ '" ".join(k for k in ("auth","task","time") if d["upstreams"].get(k) is True)'; }
if [ "$MODE" = k8s ]; then
  # через вход /health отдаёт фронт; тело gateway - запросом изнутри его пода
  HEALTH=$(in_svc gateway python -c "import urllib.request as u;print(u.urlopen('http://127.0.0.1:8000/health').read().decode())" | health_up)
  chk "GET /health upstreams all true (in gateway pod)" "auth task time" "$HEALTH"
  chk "GET / через вход (фронт)" 200 $(code $G/)
else
  HEALTH=$(curl -s $G/health | health_up)
  chk "GET /health upstreams all true" "auth task time" "$HEALTH"
  chk "GET /" 200 $(code $G/)
fi
chk "register new user" 201 $(code $G/api/auth/register -H "$J" -d "{\"email\":\"e2e-$SFX@example.com\",\"password\":\"password123\"}")
chk "register with role=admin -> role user" user $(curl -s $G/api/auth/register -H "$J" -d "{\"email\":\"e2e-adm-$SFX@example.com\",\"password\":\"password123\",\"role\":\"admin\"}" | jq_ 'd["role"]')
chk "login wrong password" 401 $(code $G/api/auth/login -H "$J" -d '{"email":"user1@example.com","password":"bad"}')

ADMIN=$(login admin@example.com); A=$(echo "$ADMIN" | jq_ 'd["access_token"]'); AR=$(echo "$ADMIN" | jq_ 'd["refresh_token"]')
U1J=$(login user1@example.com); U1=$(echo "$U1J" | jq_ 'd["access_token"]'); U1R=$(echo "$U1J" | jq_ 'd["refresh_token"]')
U2=$(login user2@example.com | jq_ 'd["access_token"]')
AID=$(curl -s $G/api/auth/me -H "Authorization: Bearer $A" | jq_ 'd["id"]')
U1ID=$(curl -s $G/api/auth/me -H "Authorization: Bearer $U1" | jq_ 'd["id"]')
U2ID=$(curl -s $G/api/auth/me -H "Authorization: Bearer $U2" | jq_ 'd["id"]')
chk "login seeded users" 1 $([ -n "$A" ] && [ -n "$U1" ] && [ -n "$U2" ] && echo 1)

echo "== Без токена -> 401"
for p in /api/auth/me /api/tasks/projects /api/tasks/tasks /api/time/time-entries /api/tasks/statistics/users /api/time/statistics/users; do
  chk "GET $p" 401 $(code $G$p)
done
chk "POST /api/tasks/tasks" 401 $(code $G/api/tasks/tasks -H "$J" -d '{"title":"x","project_id":1}')
chk "POST /api/tasks/projects" 401 $(code $G/api/tasks/projects -H "$J" -d '{"name":"x"}')

echo "== Плохие токены -> 401"
chk "garbage token" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer abc.def.ghi")
chk "refresh token as access" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer $U1R")
T_EXP=$(forge "{\"sub\":\"$U1ID\",\"role\":\"user\",\"type\":\"access\",\"exp\":-60}")
chk "expired token" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer $T_EXP")
T_NOEXP=$(forge "{\"sub\":\"$U1ID\",\"role\":\"user\",\"type\":\"access\"}")
chk "no exp" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer $T_NOEXP")
T_BADKEY=$(forge "{\"sub\":\"$U1ID\",\"role\":\"admin\",\"type\":\"access\",\"exp\":600}" not-the-key)
chk "wrong signature key" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer $T_BADKEY")
T_ROLE=$(forge "{\"sub\":\"$U1ID\",\"role\":\"superadmin\",\"type\":\"access\",\"exp\":600}")
chk "unknown role" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer $T_ROLE")
NONE=$(python3 -c "import base64,json;e=lambda o:base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b'=').decode();print(e({'alg':'none','typ':'JWT'})+'.'+e({'sub':'1','role':'admin','type':'access','exp':9999999999})+'.')")
chk "alg=none" 401 $(code $G/api/tasks/tasks -H "Authorization: Bearer $NONE")
chk "Basic instead of Bearer" 401 $(code $G/api/tasks/tasks -H "Authorization: Basic dXNlcjpwYXNz")

echo "== Маршрутизация"
chk "unknown /api/unknown" 404 $(code $G/api/unknown)
chk "prefix /api/authx" 404 $(code $G/api/authx/login)
if [ "$MODE" = k8s ]; then
  # через вход: Envoy нормализует путь до маршрутизации, gateway получает /api/auth/me -> без токена 401
  chk "path traversal via entry (normalized)" 401 $(code --path-as-is $G/api/tasks/../auth/me)
  chk "encoded traversal via entry (normalized)" 401 $(code --path-as-is $G/api/tasks/%2e%2e/auth/me)
  # сам gateway, путь как есть (urllib не схлопывает ../, в отличие от httpx)
  gw_code() { in_svc gateway python -c "import urllib.request as u, urllib.error as e
try: print(u.urlopen('http://127.0.0.1:8000$1').status)
except e.HTTPError as x: print(x.code)"; }
  chk "path traversal at gateway" 404 $(gw_code /api/tasks/../auth/me)
  chk "encoded traversal at gateway" 404 $(gw_code /api/tasks/%2e%2e/auth/me)
else
  chk "path traversal" 404 $(code --path-as-is $G/api/tasks/../auth/me)
  chk "encoded traversal" 404 $(code --path-as-is $G/api/tasks/%2e%2e/auth/me)
fi
chk "GET /api/time/projects (removed in 1.2.4)" 404 $(req "$U1" GET /api/time/projects)
chk "POST /api/time/projects (removed in 1.2.4)" 404 $(req "$U1" POST /api/time/projects '{"name":"x"}')
chk "admin GET /api/time/projects" 404 $(req "$A" GET /api/time/projects)

echo "== Создание: проекты и задачи (владелец из токена)"
PAJ=$(body "$A" POST /api/tasks/projects "{\"name\":\"admin $SFX\"}")
PA=$(echo "$PAJ" | jq_ 'd["id"]')
chk "admin creates project, owner_id = admin" "$AID" $(echo "$PAJ" | jq_ 'd["owner_id"]')
P1J=$(body "$U1" POST /api/tasks/projects "{\"name\":\"u1 $SFX\",\"owner_id\":$U2ID}")
P1=$(echo "$P1J" | jq_ 'd["id"]')
chk "user1 creates project (owner_id in body ignored)" "$U1ID" $(echo "$P1J" | jq_ 'd["owner_id"]')
P2J=$(body "$U2" POST /api/tasks/projects "{\"name\":\"u2 $SFX\"}")
P2=$(echo "$P2J" | jq_ 'd["id"]')
chk "user2 creates project" "$U2ID" $(echo "$P2J" | jq_ 'd["owner_id"]')
T1J=$(body "$U1" POST /api/tasks/tasks "{\"title\":\"T1 $SFX\",\"project_id\":$P1}")
T1=$(echo "$T1J" | jq_ 'd["id"]')
chk "user1 creates task in own project (todo)" todo $(echo "$T1J" | jq_ 'd["status"]')
chk "task owner_id = user1" "$U1ID" $(echo "$T1J" | jq_ 'd["owner_id"]')
T2J=$(body "$U2" POST /api/tasks/tasks "{\"title\":\"T2 $SFX\",\"project_id\":$P2}")
T2=$(echo "$T2J" | jq_ 'd["id"]')
chk "user2 creates task in own project" "$U2ID" $(echo "$T2J" | jq_ 'd["owner_id"]')
TNJ=$(body "$U1" POST /api/tasks/tasks "{\"title\":\"TN $SFX\"}")
TN=$(echo "$TNJ" | jq_ 'd["id"]')
chk "user1 creates task without project" "$U1ID" $(echo "$TNJ" | jq_ 'd["owner_id"]')
chk "user1 PUT status done" done $(body "$U1" PUT /api/tasks/tasks/$T1 '{"status":"done"}' | jq_ 'd["status"]')
chk "user1 POST /status in_progress" 200 $(req "$U1" POST /api/tasks/tasks/$T1/status '{"status":"in_progress"}')

echo "== Списки: user видит только свои, admin — всё"
L1P=$(body "$U1" GET /api/tasks/projects | ids)
chk "user1 projects: own" 1 $(has "$L1P" $P1)
chk "user1 projects: not user2's" 0 $(has "$L1P" $P2)
chk "user1 projects: not admin's" 0 $(has "$L1P" $PA)
chk "user1 projects: all owner_id = user1" "[$U1ID]" "$(body "$U1" GET /api/tasks/projects | jq_ 'sorted({x["owner_id"] for x in d})' | tr -d ' ')"
L2P=$(body "$U2" GET /api/tasks/projects | ids)
chk "user2 projects: own" 1 $(has "$L2P" $P2)
chk "user2 projects: not user1's" 0 $(has "$L2P" $P1)
LAP=$(body "$A" GET /api/tasks/projects | ids)
chk "admin projects: sees all three" "1 1 1" "$(has "$LAP" $PA) $(has "$LAP" $P1) $(has "$LAP" $P2)"
L1T=$(body "$U1" GET /api/tasks/tasks | ids)
chk "user1 tasks: own (T1, no-project)" "1 1" "$(has "$L1T" $T1) $(has "$L1T" $TN)"
chk "user1 tasks: not user2's" 0 $(has "$L1T" $T2)
chk "user1 tasks: all owner_id = user1" "[$U1ID]" "$(body "$U1" GET /api/tasks/tasks | jq_ 'sorted({x["owner_id"] for x in d})' | tr -d ' ')"
chk "user1 ?project_id=user2's project: empty" "" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P2" | ids)"
chk "user1 ?project_id=own" "$T1" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P1" | ids)"
L2T=$(body "$U2" GET /api/tasks/tasks | ids)
chk "user2 tasks: own, not user1's" "1 0 0" "$(has "$L2T" $T2) $(has "$L2T" $T1) $(has "$L2T" $TN)"
LAT=$(body "$A" GET /api/tasks/tasks | ids)
chk "admin tasks: sees all" "1 1 1" "$(has "$LAT" $T1) $(has "$LAT" $T2) $(has "$LAT" $TN)"

echo "== Чужое -> 404 (user1 на объекты user2 и admin)"
chk "user1 GET user2 project" 404 $(req "$U1" GET /api/tasks/projects/$P2)
chk "user1 PUT user2 project" 404 $(req "$U1" PUT /api/tasks/projects/$P2 '{"name":"hack"}')
chk "user1 DELETE user2 project" 404 $(req "$U1" DELETE /api/tasks/projects/$P2)
chk "user1 GET admin project" 404 $(req "$U1" GET /api/tasks/projects/$PA)
chk "user1 GET user2 task" 404 $(req "$U1" GET /api/tasks/tasks/$T2)
chk "user1 PUT user2 task" 404 $(req "$U1" PUT /api/tasks/tasks/$T2 '{"title":"hack"}')
chk "user1 POST /status user2 task" 404 $(req "$U1" POST /api/tasks/tasks/$T2/status '{"status":"done"}')
chk "user1 DELETE user2 task" 404 $(req "$U1" DELETE /api/tasks/tasks/$T2)
chk "user2 GET user1 project" 404 $(req "$U2" GET /api/tasks/projects/$P1)
chk "user2 GET user1 task" 404 $(req "$U2" GET /api/tasks/tasks/$T1)
chk "foreign task not changed" "T2 $SFX" "$(body "$A" GET /api/tasks/tasks/$T2 | jq_ 'd["title"]')"
chk "foreign project still exists" 200 $(req "$A" GET /api/tasks/projects/$P2)
chk "nonexistent project (same 404)" 404 $(req "$U1" GET /api/tasks/projects/999999)

echo "== Задача в чужой / несуществующий проект, перенос"
chk "user1 task in user2 project" 404 $(req "$U1" POST /api/tasks/tasks "{\"title\":\"x\",\"project_id\":$P2}")
chk "user1 task in admin project" 404 $(req "$U1" POST /api/tasks/tasks "{\"title\":\"x\",\"project_id\":$PA}")
chk "user1 task in project 0" 404 $(req "$U1" POST /api/tasks/tasks '{"title":"x","project_id":0}')
chk "admin task in project 999999" 404 $(req "$A" POST /api/tasks/tasks '{"title":"x","project_id":999999}')
chk "user1 move own task to user2 project" 404 $(req "$U1" PUT /api/tasks/tasks/$T1 "{\"project_id\":$P2}")
chk "user1 move own task to project 0" 404 $(req "$U1" PUT /api/tasks/tasks/$T1 '{"project_id":0}')
chk "task stayed in own project" "$P1" "$(body "$U1" GET /api/tasks/tasks/$T1 | jq_ 'd["project_id"]')"
chk "admin move user1 task to user2 project (other owner)" 400 $(req "$A" PUT /api/tasks/tasks/$T1 "{\"project_id\":$P2}")
TAJ=$(body "$A" POST /api/tasks/tasks "{\"title\":\"by admin $SFX\",\"project_id\":$P1}")
chk "admin task in user1 project -> owner = user1" "$U1ID" $(echo "$TAJ" | jq_ 'd["owner_id"]')

echo "== admin видит и меняет всё"
chk "admin GET user1 project" 200 $(req "$A" GET /api/tasks/projects/$P1)
chk "admin GET user2 task" 200 $(req "$A" GET /api/tasks/tasks/$T2)
chk "admin PUT user2 task (owner kept)" "$U2ID" "$(body "$A" PUT /api/tasks/tasks/$T2 '{"description":"by admin"}' | jq_ 'd["owner_id"]')"
chk "admin statistics via task (time reached)" 200 $(req "$A" GET /api/tasks/statistics/users)

echo "== Подделанные заголовки"
chk "X-User-* without token" 401 $(code $G/api/tasks/statistics/users -H "X-User-Id: 1" -H "X-User-Role: admin")
chk "user + X-User-Role: admin -> statistics" 403 $(code $G/api/tasks/statistics/users -H "Authorization: Bearer $U1" -H "X-User-Role: admin")
chk "user + X-User-Role: admin -> admin project still 404" 404 $(code $G/api/tasks/projects/$PA -H "Authorization: Bearer $U1" -H "X-User-Role: admin" -H "X-User-Id: $AID")
PHJ=$(curl -s $G/api/tasks/projects -H "Authorization: Bearer $U1" -H "X-User-Role: admin" -H "X-User-Id: $AID" -H "$J" -d "{\"name\":\"hdr $SFX\"}")
chk "user + X-User-Id: admin -> owner_id from token" "$U1ID" $(echo "$PHJ" | jq_ 'd["owner_id"]')

echo "== Время: записи на своих задачах"
E=$(body "$U1" POST /api/time/time-entries "{\"task_id\":$T1,\"minutes\":5,\"user_id\":999}")
chk "time entry user_id from token, not body(999)" "$U1ID" $(echo "$E" | jq_ 'd["user_id"]')
chk "user2 time entry on own task" 200 $(req "$U2" POST /api/time/time-entries "{\"task_id\":$T2,\"minutes\":7}")
chk "user1 sees only own entries" "[$U1ID]" "$(body "$U1" GET /api/time/time-entries | jq_ 'sorted({e["user_id"] for e in d})' | tr -d ' ')"
chk "user1 sees entry on own task" 1 "$(body "$U1" GET /api/time/time-entries | jq_ 'int(any(e["task_id"]==int("'$T1'") for e in d))')"
chk "user2 sees only own entries" "[$U2ID]" "$(body "$U2" GET /api/time/time-entries | jq_ 'sorted({e["user_id"] for e in d})' | tr -d ' ')"
chk "user1 ?user_id=user2" 403 $(code "$G/api/time/time-entries?user_id=$U2ID" -H "Authorization: Bearer $U1")
chk "user1 statistics via task" 403 $(req "$U1" GET /api/tasks/statistics/users)
chk "user1 statistics via time" 403 $(req "$U1" GET /api/time/statistics/users)
chk "admin sees all entries (user1 and user2)" "1 1" "$(body "$A" GET /api/time/time-entries | jq_ '" ".join(str(int(any(e["user_id"]==u for e in d))) for u in (int("'$U1ID'"),int("'$U2ID'")))')"
chk "admin statistics via time" 200 $(req "$A" GET /api/time/statistics/users)

echo "== Удаление: своё 204, каскад проекта"
chk "user1 DELETE own task" 204 $(req "$U1" DELETE /api/tasks/tasks/$TN)
chk "deleted task -> 404" 404 $(req "$U1" GET /api/tasks/tasks/$TN)
chk "user2 DELETE own project" 204 $(req "$U2" DELETE /api/tasks/projects/$P2)
chk "project task gone with project (admin)" 404 $(req "$A" GET /api/tasks/tasks/$T2)

echo "== refresh"
A2=$(curl -s $G/api/auth/refresh -H "$J" -d "{\"refresh_token\":\"$AR\"}" | jq_ 'd["access_token"]')
chk "admin role kept after refresh" 200 $(code $G/api/tasks/statistics/users -H "Authorization: Bearer $A2")
chk "refresh with access token" 401 $(code $G/api/auth/refresh -H "$J" -d "{\"refresh_token\":\"$A\"}")
in_auth_db psql -q -U auth_user -d auth_db -c "update users set is_active=false where email='user1@example.com'" >/dev/null
chk "inactive: login" 403 $(code $G/api/auth/login -H "$J" -d '{"email":"user1@example.com","password":"password123"}')
chk "inactive: refresh" 401 $(code $G/api/auth/refresh -H "$J" -d "{\"refresh_token\":\"$U1R\"}")
chk "inactive: /me" 401 $(code $G/api/auth/me -H "Authorization: Bearer $U1")
in_auth_db psql -q -U auth_user -d auth_db -c "update users set is_active=true where email='user1@example.com'" >/dev/null
chk "reactivated: login" 200 $(code $G/api/auth/login -H "$J" -d '{"email":"user1@example.com","password":"password123"}')

echo "== В обход gateway (из пода/контейнера gateway)"
for s in ser-task:8002/api/tasks/tasks ser-time:8003/api/time/time-entries ser-auth:8001/api/auth/me; do
  chk "direct $s no token" 401 $(in_svc gateway python -c "import httpx;print(httpx.get('http://$s').status_code)")
  chk "direct $s forged X-User-*" 401 $(in_svc gateway python -c "import httpx;print(httpx.get('http://$s',headers={'X-User-Id':'1','X-User-Role':'admin'}).status_code)")
done
chk "direct ser-task with valid token" 200 $(in_svc gateway python -c "import httpx;print(httpx.get('http://ser-task:8002/api/tasks/tasks',headers={'Authorization':'Bearer $U2'}).status_code)")

echo "== Порты наружу"
for p in $CLOSED_PORTS; do chk "localhost:$p closed" 000 $(code --max-time 2 http://localhost:$p/); done

echo "== CORS"
chk "preflight $ORIGIN" 200 $(code -X OPTIONS $G/api/tasks/tasks -H "Origin: $ORIGIN" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization")
chk "preflight evil origin" 400 $(code -X OPTIONS $G/api/tasks/tasks -H "Origin: http://evil.example" -H "Access-Control-Request-Method: GET")
chk "401 carries Allow-Origin" 1 $(curl -s -D - -o /dev/null $G/api/tasks/tasks -H "Origin: $ORIGIN" | grep -qi "^access-control-allow-origin: $ORIGIN" && echo 1)

echo; echo "PASSED $PASS, FAILED $FAIL (режим $MODE, ожидается $EXPECTED)"
[ "$FAIL" -eq 0 ]
