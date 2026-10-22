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
