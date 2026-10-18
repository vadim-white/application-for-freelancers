#!/usr/bin/env bash
# Создаёт корневой .env из .env.example и подставляет случайные секреты.
# Идемпотентен: существующий .env не перезаписывается, дописываются только
# отсутствующие ключи. Значения секретов не печатаются.
# Совместим с macOS bash 3.2 (без sed -i, без ассоциативных массивов).
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE="$ROOT/.env.example"
ENV_FILE="$ROOT/.env"

# ключи, значения которых генерируются, если в .env их нет или они пустые
SECRET_KEYS="SECRET_KEY AUTH_DB_PASSWORD TASK_DB_PASSWORD TIME_DB_PASSWORD"

[ -f "$EXAMPLE" ] || { echo "Нет файла $EXAMPLE" >&2; exit 1; }

gen_secret() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 | tr '+/' '-_' | tr -d '=\n'
  else
    echo "Нужен python3 или openssl для генерации секретов" >&2
    exit 1
  fi
}

# значение ключа в .env (последняя строка KEY=...), пусто если нет
current_value() {
  grep "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2-
}

has_key() {
  grep -q "^$1=" "$ENV_FILE"
}

is_secret() {
  case " $SECRET_KEYS " in *" $1 "*) return 0;; esac
  return 1
}

if [ ! -f "$ENV_FILE" ]; then
  : > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  created=1
else
  created=0
fi

added=""
# ключи шаблона: строки вида KEY=value (комментарии и пустые пропускаем).
# Цикл читает из подстановки процесса, а не из pipe: так он идёт в этом же shell и $added сохраняется
while read -r key; do
  if is_secret "$key"; then
    if has_key "$key" && [ -n "$(current_value "$key")" ]; then
      continue
    fi
    if has_key "$key"; then
      # ключ есть, но пуст: пересобираем файл без этой строки (без sed -i)
      tmp="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
      grep -v "^$key=" "$ENV_FILE" > "$tmp" || true
      chmod 600 "$tmp"
      mv "$tmp" "$ENV_FILE"
    fi
    # сначала в переменную: сбой gen_secret при set -e останавливает скрипт, пустое значение в файл не попадёт
    value="$(gen_secret)"
    [ -n "$value" ] || { echo "Не удалось сгенерировать значение для $key" >&2; exit 1; }
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  else
    has_key "$key" && continue
    grep "^$key=" "$EXAMPLE" | head -n 1 >> "$ENV_FILE"
  fi
  added="$added $key"
done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$EXAMPLE" | cut -d= -f1)

if [ "$created" = 1 ]; then
  echo ".env создан. Ключи:$added"
elif [ -n "$added" ]; then
  echo ".env дополнен. Добавлены ключи:$added"
else
  echo ".env уже полный, ничего не изменено"
fi
