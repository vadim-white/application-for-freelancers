#!/usr/bin/env bash
# Создаёт k8s/overlays/local/app.env и db.env из шаблонов со случайными значениями; повторно
# дописывает только недостающие или пустые ключи. Секреты не печатаются. Совместим с macOS bash 3.2.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/k8s/overlays/local"
# все ключи шаблонов — секреты, значения генерируются
FILES="app.env db.env"

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

# fill_env <шаблон> <файл>: создать файл или дописать недостающие и пустые ключи
fill_env() {
  example="$1"
  env_file="$2"
  name="$(basename "$env_file")"

  [ -f "$example" ] || { echo "Нет файла $example" >&2; exit 1; }

  if [ ! -f "$env_file" ]; then
    (umask 077; : > "$env_file")
    created=1
  else
    created=0
  fi
  chmod 600 "$env_file"

  added=""
  # подстановка процесса, а не pipe: цикл идёт в этом же shell, $added сохраняется
  while read -r key; do
    if grep -q "^$key=" "$env_file"; then
      [ -n "$(grep "^$key=" "$env_file" | tail -n 1 | cut -d= -f2-)" ] && continue
      # ключ есть, но пуст: пересобираем файл без этой строки (без sed -i)
      tmp="$(mktemp "$DIR/.$name.tmp.XXXXXX")"
      grep -v "^$key=" "$env_file" > "$tmp" || true
      chmod 600 "$tmp"
      mv "$tmp" "$env_file"
    fi
    # сначала в переменную: сбой gen_secret при set -e останавливает скрипт, пустое значение в файл не попадёт
    value="$(gen_secret)"
    [ -n "$value" ] || { echo "Не удалось сгенерировать значение для $key" >&2; exit 1; }
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
    added="$added $key"
  done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$example" | cut -d= -f1)

  if [ "$created" = 1 ]; then
    echo "$name создан. Ключи:$added"
  elif [ -n "$added" ]; then
    echo "$name дополнен. Добавлены ключи:$added"
  else
    echo "$name уже полный, ничего не изменено"
  fi
}

for f in $FILES; do
  fill_env "$DIR/$f.example" "$DIR/$f"
done

if [ -f "$DIR/secrets.env" ]; then
  echo "Найден устаревший $DIR/secrets.env (до разделения на app.env и db.env) — больше не используется, его можно удалить" >&2
fi
