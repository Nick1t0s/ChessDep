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
