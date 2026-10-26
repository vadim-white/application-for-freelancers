#!/bin/bash
# Сквозной прогон через gateway: `bash tests/smoke.sh` из корня; объекты создаёт сам, проходит на чистой базе.
# SMOKE_MODE=compose — 182 проверки, после `docker compose up --build -d --wait`, через вход http://localhost:5173 (nginx фронта);
# SMOKE_MODE=k8s — 179, после ./scripts/k8s-deploy.sh, через вход http://127.0.0.1:8080, как браузер.
# gateway :8000 наружу не опубликован ни в одном режиме (в compose это проверяет «localhost:8000 closed»).
# В k8s нет пяти проверок закрытых портов: кластер публикует на хост только 8080, они ничего не доказывают.
# Изоляцию NetworkPolicy внутри кластера smoke не проверяет.
# В k8s path traversal проверяется дважды: Envoy нормализует путь до gateway, защита gateway — изнутри его пода.
# /health через вход отдаёт фронт, /ready вне /api — оба проверяются изнутри gateway (контейнер или под); /health — по телу.
# Переопределяется: SMOKE_G, SMOKE_ORIGIN, KUBE_CONTEXT.
MODE="${SMOKE_MODE:-compose}"
case "$MODE" in
  compose)
    G="${SMOKE_G:-http://localhost:5173}"
    CLOSED_PORTS="8000 8001 8002 8003 5432"
    EXPECTED=182
    in_svc() { local s=$1; shift; docker exec "ser-$s" "$@"; }   # in_svc auth|gateway команда...
    in_auth_db() { docker exec ser-auth-db "$@"; }
    ;;
  k8s)
    KCTX="${KUBE_CONTEXT:-kind-freelance}"
    KNS=freelance-service
    G="${SMOKE_G:-http://127.0.0.1:8080}"
    CLOSED_PORTS=""
    EXPECTED=179
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
# Вложенные кавычки в "$(…)" bash 3.2 (macOS /bin/bash) разбирает неверно (JSON с \" рассыпается на слова),
# поэтому такие проверки: R=$(…); chk … "$R".
# все запросы curl идут через cu: --max-time 15, чтобы молчащий сервер не повесил прогон;
# проверка закрытых портов добавляет свой --max-time 2 (при повторе curl берёт последний)
cu() { curl --max-time 15 "$@"; }
code() { cu -s -o /dev/null -w '%{http_code}' "$@"; }
J='Content-Type: application/json'
SFX="$(date +%s)$RANDOM"
jq_() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }
login() { cu -s "$G/api/auth/login" -H "$J" -d "{\"email\":\"$1\",\"password\":\"${2:-password123}\"}"; }
# req TOKEN METHOD PATH [JSON] -> http-код
req() {
  local a=(-s -o /dev/null -w '%{http_code}' -X "$2" "$G$3" -H "Authorization: Bearer $1" -H "$J")
  [ -n "${4:-}" ] && a+=(-d "$4")
  cu "${a[@]}"
}
# body TOKEN METHOD PATH [JSON] -> тело ответа
body() {
  local a=(-s -X "$2" "$G$3" -H "Authorization: Bearer $1" -H "$J")
  [ -n "${4:-}" ] && a+=(-d "$4")
  cu "${a[@]}"
}
ids() { jq_ '" ".join(str(x["id"]) for x in d["items"])'; }  # конверт списка -> "1 2 3"
has() { case " $1 " in *" $2 "*) echo 1;; *) echo 0;; esac; }  # has "1 2 3" 2 -> 1
# токен, подписанный ключом стека, с произвольными claims (PyJWT внутри ser-auth)
forge() { # claims-json [key-expr]
  in_svc auth env CLAIMS="$1" KEY="${2:-}" python -c "
import os,time,json,jwt
c=json.loads(os.environ['CLAIMS']); now=int(time.time())
for k in ('exp','iat'):
    if k in c: c[k]=now+c[k]
print(jwt.encode(c, os.environ['KEY'] or os.environ['SECRET_KEY'], algorithm='HS256'))"; }

echo "== Публичные пути"
# /health по телу: "auth task time" для upstreams, равных true; пусто, если ответ не разобрался
health_up() { jq_ '" ".join(k for k in ("auth","task","time") if d["upstreams"].get(k) is True)'; }
# через вход /health отдаёт фронт; тело gateway - запросом изнутри его контейнера или пода
HEALTH=$(in_svc gateway python -c "import urllib.request as u;print(u.urlopen('http://127.0.0.1:8000/health').read().decode())" | health_up)
chk "GET /health upstreams all true (in gateway)" "auth task time" "$HEALTH"
chk "GET / через вход (фронт)" 200 "$(code "$G/")"
for s in auth:8001 task:8002 time:8003; do
  R=$(in_svc gateway python -c "import urllib.request as u;print(u.urlopen('http://ser-$s/ready', timeout=5).status)")
  chk "/ready ${s%%:*} (from gateway)" 200 "$R"
done
R=$(code "$G/api/auth/register" -H "$J" -d "{\"email\":\"e2e-$SFX@example.com\",\"password\":\"password123\"}"); chk "register new user" 201 "$R"
# email без учёта регистра: тот же адрес заглавными — уже занят, и по нему входят
UPPER=$(echo "e2e-$SFX@example.com" | tr '[:lower:]' '[:upper:]')
R=$(code "$G/api/auth/register" -H "$J" -d "{\"email\":\"$UPPER\",\"password\":\"password123\"}"); chk "register same email uppercase" 400 "$R"
R=$(code "$G/api/auth/login" -H "$J" -d "{\"email\":\"$UPPER\",\"password\":\"password123\"}"); chk "login email uppercase" 200 "$R"
R=$(cu -s "$G/api/auth/register" -H "$J" -d "{\"email\":\"e2e-adm-$SFX@example.com\",\"password\":\"password123\",\"role\":\"admin\"}" | jq_ 'd["role"]'); chk "register with role=admin -> role user" user "$R"
chk "login wrong password" 401 "$(code "$G/api/auth/login" -H "$J" -d '{"email":"user1@example.com","password":"bad"}')"
# date ставят и сервис, и uvicorn gateway: дубль — две строки или склейка через запятую в Envoy;
# запятая есть и в одном date, поэтому считаем GMT
R=$(cu -s -D - -o /dev/null "$G/api/auth/login" -H "$J" -d '{"email":"user1@example.com","password":"bad"}' | grep -i '^date:' | grep -o GMT | wc -l | tr -d ' ')
chk "proxied response: one date" 1 "$R"

echo "== Счётчик неудачных входов: 5 за 15 минут на email"
# Только адреса прогона: seed-пользователей smoke не запирает (их неудачи выше обнуляет вход ниже)
bad_login() { cu -s -o /dev/null -D - -w 'code %{http_code}\n' "$G/api/auth/login" -H "$J" -d "{\"email\":\"$1\",\"password\":\"${2:-bad-password}\"}" | tr -d '\r'; }
codes5() { local out=""; for _ in 1 2 3 4 5; do out="$out $(bad_login "$1" | awk '$1=="code"{print $2}')"; done; echo "$out"; }
LOCKED="e2e-adm-$SFX@example.com"
R=$(codes5 "$LOCKED"); chk "5 wrong passwords -> 401" " 401 401 401 401 401" "$R"
R=$(bad_login "$LOCKED"); chk "6th wrong password -> 429" 429 "$(echo "$R" | awk '$1=="code"{print $2}')"
RA=$(echo "$R" | awk 'tolower($1)=="retry-after:"{print $2}')
chk "429 Retry-After 1..900" 1 "$([ "$RA" -ge 1 ] 2>/dev/null && [ "$RA" -le 900 ] && echo 1)"
R=$(bad_login "$LOCKED" password123 | awk '$1=="code"{print $2}'); chk "correct password while locked -> 429" 429 "$R"
R=$(codes5 "nobody-$SFX@example.com"); chk "unknown email: 5 wrong -> 401" " 401 401 401 401 401" "$R"
R=$(bad_login "nobody-$SFX@example.com" | awk '$1=="code"{print $2}'); chk "unknown email: 6th -> 429" 429 "$R"

ADMIN=$(login admin@example.com); A=$(echo "$ADMIN" | jq_ 'd["access_token"]'); AR=$(echo "$ADMIN" | jq_ 'd["refresh_token"]')
U1J=$(login user1@example.com); U1=$(echo "$U1J" | jq_ 'd["access_token"]'); U1R=$(echo "$U1J" | jq_ 'd["refresh_token"]')
U2=$(login user2@example.com | jq_ 'd["access_token"]')
AID=$(cu -s "$G/api/auth/me" -H "Authorization: Bearer $A" | jq_ 'd["id"]')
U1ID=$(cu -s "$G/api/auth/me" -H "Authorization: Bearer $U1" | jq_ 'd["id"]')
U2ID=$(cu -s "$G/api/auth/me" -H "Authorization: Bearer $U2" | jq_ 'd["id"]')
chk "login seeded users" 1 "$([ -n "$A" ] && [ -n "$U1" ] && [ -n "$U2" ] && echo 1)"

echo "== Без токена -> 401"
for p in /api/auth/me /api/auth/users /api/tasks/projects /api/tasks/tasks /api/time/time-entries /api/tasks/statistics/users /api/time/statistics/users; do
  chk "GET $p" 401 "$(code "$G$p")"
done
chk "POST /api/tasks/tasks" 401 "$(code "$G/api/tasks/tasks" -H "$J" -d '{"title":"x","project_id":1}')"
chk "POST /api/tasks/projects" 401 "$(code "$G/api/tasks/projects" -H "$J" -d '{"name":"x"}')"

echo "== Список пользователей: только admin"
chk "user GET /api/auth/users" 403 "$(code "$G/api/auth/users" -H "Authorization: Bearer $U1")"
R=$(body "$A" GET "/api/auth/users?limit=1" | jq_ 'sorted(d)==["items","limit","offset","total"] and len(d["items"])==1 and d["total"]>=3'); chk "admin list: envelope" True "$R"
R=$(body "$A" GET "/api/auth/users?q=E2E-$SFX" | jq_ '[u["email"] for u in d["items"]]'); chk "admin list: q finds this run's user" "['e2e-$SFX@example.com']" "$R"
R=$(body "$A" GET "/api/auth/users?id=$U1ID&id=$U2ID&sort=email" | jq_ 'd["total"]'); chk "admin list: two ids" 2 "$R"
chk "admin list: limit=201" 422 "$(code "$G/api/auth/users?limit=201" -H "Authorization: Bearer $A")"

echo "== Плохие токены -> 401"
chk "garbage token" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer abc.def.ghi")"
chk "refresh token as access" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer $U1R")"
T_EXP=$(forge "{\"sub\":\"$U1ID\",\"role\":\"user\",\"type\":\"access\",\"exp\":-60}")
chk "expired token" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer $T_EXP")"
T_NOEXP=$(forge "{\"sub\":\"$U1ID\",\"role\":\"user\",\"type\":\"access\"}")
chk "no exp" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer $T_NOEXP")"
T_BADKEY=$(forge "{\"sub\":\"$U1ID\",\"role\":\"admin\",\"type\":\"access\",\"exp\":600}" not-the-stack-key-but-32-bytes-or-more)
chk "wrong signature key" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer $T_BADKEY")"
T_ROLE=$(forge "{\"sub\":\"$U1ID\",\"role\":\"superadmin\",\"type\":\"access\",\"exp\":600}")
chk "unknown role" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer $T_ROLE")"
NONE=$(python3 -c "import base64,json;e=lambda o:base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b'=').decode();print(e({'alg':'none','typ':'JWT'})+'.'+e({'sub':'1','role':'admin','type':'access','exp':9999999999})+'.')")
chk "alg=none" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Bearer $NONE")"
chk "Basic instead of Bearer" 401 "$(code "$G/api/tasks/tasks" -H "Authorization: Basic dXNlcjpwYXNz")"

echo "== Маршрутизация"
chk "unknown /api/unknown" 404 "$(code "$G/api/unknown")"
chk "prefix /api/authx" 404 "$(code "$G/api/authx/login")"
if [ "$MODE" = k8s ]; then
  # через вход: Envoy нормализует путь до маршрутизации, gateway получает /api/auth/me -> без токена 401
  chk "path traversal via entry (normalized)" 401 "$(code --path-as-is "$G/api/tasks/../auth/me")"
  chk "encoded traversal via entry (normalized)" 401 "$(code --path-as-is "$G/api/tasks/%2e%2e/auth/me")"
  # сам gateway, путь как есть (urllib не схлопывает ../, в отличие от httpx)
  gw_code() { in_svc gateway python -c "import urllib.request as u, urllib.error as e
try: print(u.urlopen('http://127.0.0.1:8000$1').status)
except e.HTTPError as x: print(x.code)"; }
  chk "path traversal at gateway" 404 "$(gw_code /api/tasks/../auth/me)"
  chk "encoded traversal at gateway" 404 "$(gw_code /api/tasks/%2e%2e/auth/me)"
else
  # через вход (nginx фронта) → gateway
  chk "path traversal" 404 "$(code --path-as-is "$G/api/tasks/../auth/me")"
  chk "encoded traversal" 404 "$(code --path-as-is "$G/api/tasks/%2e%2e/auth/me")"
fi
chk "GET /api/time/projects (removed in 1.2.4)" 404 "$(req "$U1" GET /api/time/projects)"
chk "POST /api/time/projects (removed in 1.2.4)" 404 "$(req "$U1" POST /api/time/projects '{"name":"x"}')"
chk "admin GET /api/time/projects" 404 "$(req "$A" GET /api/time/projects)"

echo "== Создание: проекты и задачи (владелец из токена)"
PAJ=$(body "$A" POST /api/tasks/projects "{\"name\":\"admin $SFX\"}")
PA=$(echo "$PAJ" | jq_ 'd["id"]')
chk "admin creates project, owner_id = admin" "$AID" "$(echo "$PAJ" | jq_ 'd["owner_id"]')"
P1J=$(body "$U1" POST /api/tasks/projects "{\"name\":\"u1 $SFX\",\"owner_id\":$U2ID}")
P1=$(echo "$P1J" | jq_ 'd["id"]')
chk "user1 creates project (owner_id in body ignored)" "$U1ID" "$(echo "$P1J" | jq_ 'd["owner_id"]')"
P2J=$(body "$U2" POST /api/tasks/projects "{\"name\":\"u2 $SFX\"}")
P2=$(echo "$P2J" | jq_ 'd["id"]')
chk "user2 creates project" "$U2ID" "$(echo "$P2J" | jq_ 'd["owner_id"]')"
T1J=$(body "$U1" POST /api/tasks/tasks "{\"title\":\"T1 $SFX\",\"project_id\":$P1}")
T1=$(echo "$T1J" | jq_ 'd["id"]')
chk "user1 creates task in own project (todo)" todo "$(echo "$T1J" | jq_ 'd["status"]')"
chk "task owner_id = user1" "$U1ID" "$(echo "$T1J" | jq_ 'd["owner_id"]')"
T2J=$(body "$U2" POST /api/tasks/tasks "{\"title\":\"T2 $SFX\",\"project_id\":$P2}")
T2=$(echo "$T2J" | jq_ 'd["id"]')
chk "user2 creates task in own project" "$U2ID" "$(echo "$T2J" | jq_ 'd["owner_id"]')"
TNJ=$(body "$U1" POST /api/tasks/tasks "{\"title\":\"TN $SFX\"}")
TN=$(echo "$TNJ" | jq_ 'd["id"]')
chk "user1 creates task without project" "$U1ID" "$(echo "$TNJ" | jq_ 'd["owner_id"]')"
chk "user1 PATCH status done" "done" "$(body "$U1" PATCH "/api/tasks/tasks/$T1" '{"status":"done"}' | jq_ 'd["status"]')"
chk "user1 POST /status in_progress" 200 "$(req "$U1" POST "/api/tasks/tasks/$T1/status" '{"status":"in_progress"}')"

echo "== Списки: user видит только свои, admin — всё"
# база живёт между прогонами: объекты прогона — первые при сортировке по умолчанию (новые сверху),
# задачи user1 ищутся ещё и в проекте прогона P1, где только его задачи
L1P=$(body "$U1" GET /api/tasks/projects | ids)
chk "user1 projects: own" 1 "$(has "$L1P" "$P1")"
chk "user1 projects: not user2's" 0 "$(has "$L1P" "$P2")"
chk "user1 projects: not admin's" 0 "$(has "$L1P" "$PA")"
chk "user1 projects: all owner_id = user1" "[$U1ID]" "$(body "$U1" GET /api/tasks/projects | jq_ 'sorted({x["owner_id"] for x in d["items"]})' | tr -d ' ')"
L2P=$(body "$U2" GET /api/tasks/projects | ids)
chk "user2 projects: own" 1 "$(has "$L2P" "$P2")"
chk "user2 projects: not user1's" 0 "$(has "$L2P" "$P1")"
LAP=$(body "$A" GET /api/tasks/projects | ids)
chk "admin projects: sees all three" "1 1 1" "$(has "$LAP" "$PA") $(has "$LAP" "$P1") $(has "$LAP" "$P2")"
L1T=$(body "$U1" GET /api/tasks/tasks | ids)
chk "user1 tasks: own (T1, no-project)" "1 1" "$(has "$L1T" "$T1") $(has "$L1T" "$TN")"
chk "user1 tasks: not user2's" 0 "$(has "$L1T" "$T2")"
chk "user1 tasks: all owner_id = user1" "[$U1ID]" "$(body "$U1" GET /api/tasks/tasks | jq_ 'sorted({x["owner_id"] for x in d["items"]})' | tr -d ' ')"
chk "user1 ?project_id=user2's project: empty" "" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P2" | ids)"
chk "user1 ?project_id=own" "$T1" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P1" | ids)"
L2T=$(body "$U2" GET /api/tasks/tasks | ids)
chk "user2 tasks: own, not user1's" "1 0 0" "$(has "$L2T" "$T2") $(has "$L2T" "$T1") $(has "$L2T" "$TN")"
LAT=$(body "$A" GET /api/tasks/tasks | ids)
chk "admin tasks: sees all" "1 1 1" "$(has "$LAT" "$T1") $(has "$LAT" "$T2") $(has "$LAT" "$TN")"
R=$(body "$U1" GET "/api/tasks/tasks?project_id=$P1" | jq_ 'sorted(d)==["items","limit","offset","total"] and d["total"]==1 and d["limit"]==50'); chk "tasks list: envelope, total, limit 50" True "$R"
R=$(body "$U1" GET /api/tasks/projects | jq_ 'sorted(d)==["items","limit","offset","total"] and d["total"]>=1 and d["limit"]==50'); chk "projects list: envelope, limit 50" True "$R"
chk "tasks list: limit=201" 422 "$(req "$U1" GET "/api/tasks/tasks?limit=201")"
chk "projects list: limit=201" 422 "$(req "$U1" GET "/api/tasks/projects?limit=201")"
chk "tasks list: sort=bogus" 422 "$(req "$U1" GET "/api/tasks/tasks?sort=bogus")"
chk "projects list: sort=bogus" 422 "$(req "$U1" GET "/api/tasks/projects?sort=bogus")"
LNT=$(body "$U1" GET "/api/tasks/tasks?project_id=none" | ids)
chk "user1 ?project_id=none: TN, not T1" "1 0" "$(has "$LNT" "$TN") $(has "$LNT" "$T1")"
chk "user1 ?status=done&status=in_progress in P1" "$T1" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P1&status=done&status=in_progress" | ids)"

echo "== Чужое -> 404 (user1 на объекты user2 и admin)"
chk "user1 GET user2 project" 404 "$(req "$U1" GET "/api/tasks/projects/$P2")"
chk "user1 PATCH user2 project" 404 "$(req "$U1" PATCH "/api/tasks/projects/$P2" '{"name":"hack"}')"
chk "user1 DELETE user2 project" 404 "$(req "$U1" DELETE "/api/tasks/projects/$P2")"
chk "user1 GET admin project" 404 "$(req "$U1" GET "/api/tasks/projects/$PA")"
chk "user1 GET user2 task" 404 "$(req "$U1" GET "/api/tasks/tasks/$T2")"
chk "user1 PATCH user2 task" 404 "$(req "$U1" PATCH "/api/tasks/tasks/$T2" '{"title":"hack"}')"
chk "user1 POST /status user2 task" 404 "$(req "$U1" POST "/api/tasks/tasks/$T2/status" '{"status":"done"}')"
chk "user1 DELETE user2 task" 404 "$(req "$U1" DELETE "/api/tasks/tasks/$T2")"
chk "user2 GET user1 project" 404 "$(req "$U2" GET "/api/tasks/projects/$P1")"
chk "user2 GET user1 task" 404 "$(req "$U2" GET "/api/tasks/tasks/$T1")"
chk "foreign task not changed" "T2 $SFX" "$(body "$A" GET "/api/tasks/tasks/$T2" | jq_ 'd["title"]')"
chk "foreign project still exists" 200 "$(req "$A" GET "/api/tasks/projects/$P2")"
chk "nonexistent project (same 404)" 404 "$(req "$U1" GET /api/tasks/projects/999999)"

echo "== Задача в чужой / несуществующий проект, перенос"
R=$(req "$U1" POST /api/tasks/tasks "{\"title\":\"x\",\"project_id\":$P2}"); chk "user1 task in user2 project" 404 "$R"
R=$(req "$U1" POST /api/tasks/tasks "{\"title\":\"x\",\"project_id\":$PA}"); chk "user1 task in admin project" 404 "$R"
chk "user1 task in project 0" 404 "$(req "$U1" POST /api/tasks/tasks '{"title":"x","project_id":0}')"
chk "admin task in project 999999" 404 "$(req "$A" POST /api/tasks/tasks '{"title":"x","project_id":999999}')"
R=$(req "$U1" PATCH "/api/tasks/tasks/$T1" "{\"project_id\":$P2}"); chk "user1 move own task to user2 project" 404 "$R"
chk "user1 move own task to project 0" 404 "$(req "$U1" PATCH "/api/tasks/tasks/$T1" '{"project_id":0}')"
chk "task stayed in own project" "$P1" "$(body "$U1" GET "/api/tasks/tasks/$T1" | jq_ 'd["project_id"]')"
R=$(req "$A" PATCH "/api/tasks/tasks/$T1" "{\"project_id\":$P2}"); chk "admin move user1 task to user2 project (other owner)" 400 "$R"
TAJ=$(body "$A" POST /api/tasks/tasks "{\"title\":\"by admin $SFX\",\"project_id\":$P1}")
TA=$(echo "$TAJ" | jq_ 'd["id"]')
chk "admin task in user1 project -> owner = user1" "$U1ID" "$(echo "$TAJ" | jq_ 'd["owner_id"]')"
# по lower: «by admin …» раньше «T1 …»
chk "user1 P1 sort=title" "$TA $T1" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P1&sort=title" | ids)"
chk "user1 P1 sort=-title" "$T1 $TA" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P1&sort=-title" | ids)"
# счётчик и превью карточки: активные задачи проекта, первые по созданию; P1 среди новых проектов user1
p1card() { body "$U1" GET /api/tasks/projects | jq_ 'next(" ".join([str(p["tasks_count"])]+[str(t["id"]) for t in p["tasks_preview"]]) for p in d["items"] if p["id"]=='"$P1"')'; }
chk "user1 P1 in projects list: tasks_count and preview" "2 $T1 $TA" "$(p1card)"

echo "== PATCH: нет поля - не трогать, null - очистить; PUT удалён"
chk "PUT task -> 405" 405 "$(req "$U1" PUT "/api/tasks/tasks/$TN" '{"title":"x"}')"
chk "PUT project -> 405" 405 "$(req "$U1" PUT "/api/tasks/projects/$P1" '{"name":"x"}')"
chk "PATCH task unknown field" 422 "$(req "$U1" PATCH "/api/tasks/tasks/$TN" '{"titel":"x"}')"
chk "PATCH task title null" 422 "$(req "$U1" PATCH "/api/tasks/tasks/$TN" '{"title":null}')"
chk "PATCH task title empty" 422 "$(req "$U1" PATCH "/api/tasks/tasks/$TN" '{"title":"   "}')"
LONG=$(python3 -c 'print("x" * 256)')
chk "PATCH task title 256 chars" 422 "$(req "$U1" PATCH "/api/tasks/tasks/$TN" "{\"title\":\"$LONG\"}")"
R1=$(body "$U1" PATCH "/api/tasks/tasks/$TN" '{"description":"note"}' | jq_ 'd["description"]')
R2=$(body "$U1" PATCH "/api/tasks/tasks/$TN" '{"description":null}' | jq_ 'd["description"]')
chk "TN description set, then null clears" "note None" "$R1 $R2"
R1=$(body "$U1" PATCH "/api/tasks/tasks/$TN" '{"deadline":"2026-03-01T12:00:00Z"}' | jq_ 'd["deadline"]')
R2=$(body "$U1" PATCH "/api/tasks/tasks/$TN" '{"deadline":null}' | jq_ 'd["deadline"]')
chk "TN deadline with Z set, then null clears" "2026-03-01T12:00:00Z None" "$R1 $R2"
# TN в P1 и обратно до второй проверки p1card: счётчик P1 не меняется
R1=$(body "$U1" PATCH "/api/tasks/tasks/$TN" "{\"project_id\":$P1}" | jq_ 'd["project_id"]')
R2=$(body "$U1" PATCH "/api/tasks/tasks/$TN" '{"project_id":null}' | jq_ 'd["project_id"]')
R3=$(has "$(body "$U1" GET "/api/tasks/tasks?project_id=none" | ids)" "$TN")
chk "TN into P1, then project_id null -> back without project" "$P1 None 1" "$R1 $R2 $R3"

echo "== admin видит и меняет всё"
chk "admin GET user1 project" 200 "$(req "$A" GET "/api/tasks/projects/$P1")"
chk "admin GET user2 task" 200 "$(req "$A" GET "/api/tasks/tasks/$T2")"
chk "admin PATCH user2 task (owner kept)" "$U2ID" "$(body "$A" PATCH "/api/tasks/tasks/$T2" '{"description":"by admin"}' | jq_ 'd["owner_id"]')"
chk "admin statistics via task (time reached)" 200 "$(req "$A" GET /api/tasks/statistics/users)"

echo "== Подделанные заголовки"
chk "X-User-* without token" 401 "$(code "$G/api/tasks/statistics/users" -H "X-User-Id: 1" -H "X-User-Role: admin")"
chk "user + X-User-Role: admin -> statistics" 403 "$(code "$G/api/tasks/statistics/users" -H "Authorization: Bearer $U1" -H "X-User-Role: admin")"
chk "user + X-User-Role: admin -> admin project still 404" 404 "$(code "$G/api/tasks/projects/$PA" -H "Authorization: Bearer $U1" -H "X-User-Role: admin" -H "X-User-Id: $AID")"
PHJ=$(cu -s "$G/api/tasks/projects" -H "Authorization: Bearer $U1" -H "X-User-Role: admin" -H "X-User-Id: $AID" -H "$J" -d "{\"name\":\"hdr $SFX\"}")
chk "user + X-User-Id: admin -> owner_id from token" "$U1ID" "$(echo "$PHJ" | jq_ 'd["owner_id"]')"
# PATCH имени архивного проекта не снимает архив: PUT без is_active снимал
PH=$(echo "$PHJ" | jq_ 'd["id"]')
req "$U1" PATCH "/api/tasks/projects/$PH" '{"is_active":false}' >/dev/null
chk "PATCH name of archived project keeps archive" False "$(body "$U1" PATCH "/api/tasks/projects/$PH" "{\"name\":\"hdr2 $SFX\"}" | jq_ 'd["is_active"]')"

echo "== Время: записи на своих задачах"
# даты в прошлом: ручная запись не может уходить в будущее
T_FROM="2026-01-01T10:00:00Z"; T_TO="2026-01-01T10:05:00Z"
E=$(body "$U1" POST /api/time/time-entries "{\"task_id\":$T1,\"started_at\":\"$T_FROM\",\"stopped_at\":\"$T_TO\",\"user_id\":999}")
chk "time entry user_id from token, not body(999)" "$U1ID" "$(echo "$E" | jq_ 'd["user_id"]')"
R=$(req "$U2" POST /api/time/time-entries "{\"task_id\":$T2,\"started_at\":\"$T_FROM\",\"stopped_at\":\"$T_TO\"}"); chk "user2 time entry on own task" 201 "$R"
chk "user1 sees only own entries" "[$U1ID]" "$(body "$U1" GET /api/time/time-entries | jq_ 'sorted({e["user_id"] for e in d["items"]})' | tr -d ' ')"
# пользователь постоянный, записей за прогоны набралось больше страницы: свою задачу берём фильтром
chk "user1 sees entry on own task" 1 "$(body "$U1" GET "/api/time/time-entries?task_id=$T1" | jq_ 'int(d["total"]>0)')"
chk "user2 sees only own entries" "[$U2ID]" "$(body "$U2" GET /api/time/time-entries | jq_ 'sorted({e["user_id"] for e in d["items"]})' | tr -d ' ')"
chk "user1 ?user_id=user2" 403 "$(code "$G/api/time/time-entries?user_id=$U2ID" -H "Authorization: Bearer $U1")"
chk "user1 statistics via task" 403 "$(req "$U1" GET /api/tasks/statistics/users)"
chk "user1 statistics via time" 403 "$(req "$U1" GET /api/time/statistics/users)"
# база живёт между прогонами, а список постраничный: чужие записи admin берёт по user_id
A1=$(body "$A" GET "/api/time/time-entries?user_id=$U1ID" | jq_ 'int(d["total"]>0)')
A2=$(body "$A" GET "/api/time/time-entries?user_id=$U2ID" | jq_ 'int(d["total"]>0)')
chk "admin sees entries of user1 and user2" "1 1" "$A1 $A2"
chk "admin statistics via time (entries_count, total_seconds)" 1 "$(body "$A" GET /api/time/statistics/users | jq_ 'int(len(d)>0 and all("entries_count" in r and "total_seconds" in r for r in d))')"
# правка и удаление: своя запись, чужая — 404, как у задач
E2=$(body "$U1" POST /api/time/time-entries "{\"task_id\":$T1,\"started_at\":\"$T_FROM\",\"stopped_at\":\"$T_TO\"}")
E2ID=$(echo "$E2" | jq_ 'd["id"]')
chk "user1 PATCH own entry recalculates duration" 600 "$(body "$U1" PATCH "/api/time/time-entries/$E2ID" '{"stopped_at":"2026-01-01T10:10:00Z"}' | jq_ 'd["duration_seconds"]')"
R=$(req "$U1" PATCH "/api/time/time-entries/$E2ID" '{"stopped_at":"2025-12-31T10:00:00Z"}'); chk "user1 PATCH stopped before started" 422 "$R"
chk "user1 PATCH own entry unknown field (user_id)" 422 "$(req "$U1" PATCH "/api/time/time-entries/$E2ID" '{"user_id":999}')"
chk "user2 PATCH user1 entry" 404 "$(req "$U2" PATCH "/api/time/time-entries/$E2ID" '{"description":"x"}')"
chk "user2 DELETE user1 entry" 404 "$(req "$U2" DELETE "/api/time/time-entries/$E2ID")"
chk "user1 DELETE own entry" 204 "$(req "$U1" DELETE "/api/time/time-entries/$E2ID")"
chk "user1 DELETE entry again" 404 "$(req "$U1" DELETE "/api/time/time-entries/$E2ID")"

echo "== Таймер"
R=$(req "$U1" POST /api/time/timer/start "{\"task_id\":$T1}"); chk "timer start" 201 "$R"
chk "timer running on started task" "$T1" "$(body "$U1" GET /api/time/timer | jq_ 'd["entry"]["task_id"]')"
R=$(body "$U1" POST /api/time/timer/start "{\"task_id\":$TN}")
chk "timer start other task stops running" "$T1 $TN" "$(echo "$R" | jq_ 'str(d["stopped"]["task_id"])+" "+str(d["entry"]["task_id"])')"
chk "timer stop" "$TN" "$(body "$U1" POST /api/time/timer/stop | jq_ 'd["stopped"]["task_id"]')"
chk "timer stop again -> null" None "$(body "$U1" POST /api/time/timer/stop | jq_ 'd["stopped"]')"
# задачу time спрашивает у task с токеном пользователя
R=$(req "$U1" POST /api/time/timer/start "{\"task_id\":$T2}"); chk "timer start on user2 task" 404 "$R"
chk "timer start on nonexistent task" 404 "$(req "$U1" POST /api/time/timer/start '{"task_id":999999}')"
# идущий таймер архивация задачи не останавливает: стоп после неё закрывает запись
body "$U1" POST /api/time/timer/start "{\"task_id\":$T1}" >/dev/null
req "$U1" PATCH "/api/tasks/tasks/$T1" '{"is_active":false}' >/dev/null
R=$(req "$U1" POST /api/time/timer/start "{\"task_id\":$T1}"); chk "timer start on archived task" 409 "$R"
chk "timer stop after archive" "$T1" "$(body "$U1" POST /api/time/timer/stop | jq_ 'd["stopped"]["task_id"]')"
chk "user1 P1 ?is_active=false -> archived T1" "$T1" "$(body "$U1" GET "/api/tasks/tasks?project_id=$P1&is_active=false" | ids)"
chk "user1 P1 in projects list: archived T1 not counted" "1 $TA" "$(p1card)"

echo "== Удаление: своё 204, каскад проекта"
chk "user1 DELETE own task" 204 "$(req "$U1" DELETE "/api/tasks/tasks/$TN")"
chk "deleted task -> 404" 404 "$(req "$U1" GET "/api/tasks/tasks/$TN")"
chk "user2 DELETE own project" 204 "$(req "$U2" DELETE "/api/tasks/projects/$P2")"
chk "project task gone with project (admin)" 404 "$(req "$A" GET "/api/tasks/tasks/$T2")"

echo "== refresh"
A2=$(cu -s "$G/api/auth/refresh" -H "$J" -d "{\"refresh_token\":\"$AR\"}" | jq_ 'd["access_token"]')
chk "admin role kept after refresh" 200 "$(code "$G/api/tasks/statistics/users" -H "Authorization: Bearer $A2")"
R=$(code "$G/api/auth/refresh" -H "$J" -d "{\"refresh_token\":\"$A\"}"); chk "refresh with access token" 401 "$R"
# отключает admin через API; упадёт прогон до включения — user1 останется отключённым,
# включить: PATCH /api/auth/users/{id} {"is_active":true} от admin
req "$A" PATCH "/api/auth/users/$U1ID" '{"is_active":false}' >/dev/null
chk "inactive: login" 403 "$(code "$G/api/auth/login" -H "$J" -d '{"email":"user1@example.com","password":"password123"}')"
R=$(code "$G/api/auth/refresh" -H "$J" -d "{\"refresh_token\":\"$U1R\"}"); chk "inactive: refresh" 401 "$R"
chk "inactive: /me" 401 "$(code "$G/api/auth/me" -H "Authorization: Bearer $U1")"
req "$A" PATCH "/api/auth/users/$U1ID" '{"is_active":true}' >/dev/null
chk "reactivated: login" 200 "$(code "$G/api/auth/login" -H "$J" -d '{"email":"user1@example.com","password":"password123"}')"

echo "== Смена роли и отключение (admin)"
EJ=$(login "e2e-$SFX@example.com"); E=$(echo "$EJ" | jq_ 'd["access_token"]'); ER=$(echo "$EJ" | jq_ 'd["refresh_token"]')
EID=$(cu -s "$G/api/auth/me" -H "Authorization: Bearer $E" | jq_ 'd["id"]')
chk "user PATCH /api/auth/users/{id}" 403 "$(req "$U1" PATCH "/api/auth/users/$EID" '{"role":"admin"}')"
chk "admin PATCH self" 409 "$(req "$A" PATCH "/api/auth/users/$AID" '{"role":"user"}')"
chk "admin PATCH unknown field" 422 "$(req "$A" PATCH "/api/auth/users/$EID" '{"full_name":"x"}')"
chk "admin PATCH nonexistent user" 404 "$(req "$A" PATCH /api/auth/users/999999 '{"is_active":false}')"
chk "admin promotes this run's user" admin "$(body "$A" PATCH "/api/auth/users/$EID" '{"role":"admin"}' | jq_ 'd["role"]')"
EA=$(cu -s "$G/api/auth/refresh" -H "$J" -d "{\"refresh_token\":\"$ER\"}" | jq_ 'd["access_token"]')
chk "promoted: statistics after refresh" 200 "$(req "$EA" GET /api/tasks/statistics/users)"
# повышенный не остаётся admin: иначе admin в базе копятся от прогона к прогону
R=$(body "$A" PATCH "/api/auth/users/$EID" '{"role":"user","is_active":false}' | jq_ 'd["role"]+" "+str(d["is_active"])')
chk "admin demotes and disables this run's user" "user False" "$R"
R=$(in_auth_db psql -tA -U auth_user -d auth_db -c "select count(*) from user_audit where target_id=$EID")
chk "user_audit rows for this run's user (role x2, is_active)" 3 "$R"

echo "== В обход gateway (из пода/контейнера gateway)"
for s in ser-task:8002/api/tasks/tasks ser-time:8003/api/time/time-entries ser-auth:8001/api/auth/me; do
  R=$(in_svc gateway python -c "import httpx;print(httpx.get('http://$s').status_code)"); chk "direct $s no token" 401 "$R"
  R=$(in_svc gateway python -c "import httpx;print(httpx.get('http://$s',headers={'X-User-Id':'1','X-User-Role':'admin'}).status_code)"); chk "direct $s forged X-User-*" 401 "$R"
done
R=$(in_svc gateway python -c "import httpx;print(httpx.get('http://ser-task:8002/api/tasks/tasks',headers={'Authorization':'Bearer $U2'}).status_code)"); chk "direct ser-task with valid token" 200 "$R"

echo "== Порты наружу"
for p in $CLOSED_PORTS; do chk "localhost:$p closed" 000 "$(code --max-time 2 "http://localhost:$p/")"; done

echo "== CORS"
chk "preflight $ORIGIN" 200 "$(code -X OPTIONS "$G/api/tasks/tasks" -H "Origin: $ORIGIN" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization")"
chk "preflight evil origin" 400 "$(code -X OPTIONS "$G/api/tasks/tasks" -H "Origin: http://evil.example" -H "Access-Control-Request-Method: GET")"
chk "401 carries Allow-Origin" 1 "$(cu -s -D - -o /dev/null "$G/api/tasks/tasks" -H "Origin: $ORIGIN" | grep -qi "^access-control-allow-origin: $ORIGIN" && echo 1)"

echo; echo "PASSED $PASS, FAILED $FAIL (режим $MODE, ожидается $EXPECTED)"
# пропущенная проверка (пустой цикл, ранний выход ветки) не даёт FAIL, но и не даёт PASS: сверяем число
[ "$PASS" -eq "$EXPECTED" ] || echo "пройдено $PASS из ожидаемых $EXPECTED"
[ "$FAIL" -eq 0 ] && [ "$PASS" -eq "$EXPECTED" ]
