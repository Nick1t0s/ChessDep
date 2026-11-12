# Цель
HTTPS в nginx: при наличии сертификатов — 443 и редирект с 80, без них — как сейчас; скрипт самоподписанного сертификата для разработки.

# Контекст
Прочитай сначала: `docs/contracts-spectate.md` (п. 9), текущие `nginx/Dockerfile`, `nginx/nginx.conf`, `docker-compose.yml` (сервис `nginx`), `.env.example`, `.gitignore`.

# Область
Создать: `nginx/conf/app.locations`, `nginx/conf/http.conf.template`, `nginx/conf/https.conf.template`, `nginx/40-chessdep-conf.sh`, `scripts/gen-dev-cert.sh`, `certs/.gitkeep` (пустой). Изменить: `nginx/Dockerfile`, `docker-compose.yml` (только сервис `nginx`), `.env.example`. Удалить: `nginx/nginx.conf` (`git rm`).

# Контракт и что сделать
1. `nginx/conf/app.locations` — **весь текущий `server { ... }` из `nginx/nginx.conf` без строк `server {`, `listen 80;` и закрывающей `}`**, то есть директивы `server_tokens`, `client_max_body_size`, `root`, три `add_header`, `resolver`, `set $api_upstream`, все `location`. Содержимое переносится без изменений.

2. `nginx/conf/http.conf.template`, дословно:
```nginx
server {
    listen 80;
    include /etc/nginx/chessdep/app.locations;
}
```

3. `nginx/conf/https.conf.template`, дословно:
```nginx
server {
    listen 80;
    server_tokens off;
    location / { return 301 https://$host:${HTTPS_PORT}$request_uri; }
}
server {
    listen 443 ssl;
    http2 on;
    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    add_header Strict-Transport-Security "max-age=31536000" always;
    include /etc/nginx/chessdep/app.locations;
}
```

4. `nginx/40-chessdep-conf.sh`, дословно:
```sh
#!/bin/sh
# Выбор режима: есть сертификаты — HTTPS (443 + редирект с 80), нет — только HTTP.
set -e
if [ -f /etc/nginx/certs/fullchain.pem ] && [ -f /etc/nginx/certs/privkey.pem ]; then
  tpl=/etc/nginx/chessdep/https.conf.template
  echo "chessdep: HTTPS mode"
else
  tpl=/etc/nginx/chessdep/http.conf.template
  echo "chessdep: HTTP mode (no certs in /etc/nginx/certs)"
fi
HTTPS_PORT="${HTTPS_PORT:-8443}" envsubst '${HTTPS_PORT}' < "$tpl" > /etc/nginx/conf.d/chessdep.conf
```

5. `nginx/Dockerfile`, дословно:
```dockerfile
FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY conf/ /etc/nginx/chessdep/
COPY 40-chessdep-conf.sh /docker-entrypoint.d/40-chessdep-conf.sh
RUN chmod +x /docker-entrypoint.d/40-chessdep-conf.sh
```

6. `docker-compose.yml`, сервис `nginx`: `ports` → `["${HTTP_PORT:-8080}:80", "${HTTPS_PORT:-8443}:443"]`; `volumes` → добавить `"./certs:/etc/nginx/certs:ro"` к существующему; добавить `environment: {HTTPS_PORT: "${HTTPS_PORT:-8443}"}`. Остальное не трогать.

7. `.env.example` — добавить в конец:
```
HTTPS_PORT=8443
# HTTPS: положите certs/fullchain.pem и certs/privkey.pem (для разработки: bash scripts/gen-dev-cert.sh),
# затем COOKIE_SECURE=true и добавьте https://<хост>:8443 в ALLOWED_ORIGINS.
```

8. `scripts/gen-dev-cert.sh` (исполняемый, `chmod +x`):
```bash
#!/usr/bin/env bash
# Самоподписанный сертификат для localhost (только для разработки).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p certs
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/certs:/certs" alpine/openssl \
  req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
  -keyout /certs/privkey.pem -out /certs/fullchain.pem
echo "Готово: certs/fullchain.pem и certs/privkey.pem. Перезапустите: docker compose up -d --build nginx"
```

# Готово, когда
Все четыре команды (из корня репозитория) завершаются успешно:
```bash
docker compose config -q
docker build -q -t chessdep-nginx-check nginx
docker run --rm chessdep-nginx-check nginx -t                                  # вывод содержит "HTTP mode" и "test is successful"
tmp=$(mktemp -d) && docker run --rm --user "$(id -u):$(id -g)" -v "$tmp:/certs" alpine/openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -keyout /certs/privkey.pem -out /certs/fullchain.pem && docker run --rm -v "$tmp:/etc/nginx/certs:ro" chessdep-nginx-check nginx -t   # вывод содержит "HTTPS mode" и "test is successful"
```

# Нельзя
- Менять файлы вне «Область».
- Менять контракт (`docs/contracts-spectate.md`), добавлять эндпоинты, поля или зависимости, которых нет в контракте и задаче.
- Во фронтенде: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `style=` и `on*=` в HTML, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, а описать проблему в SUMMARY.
