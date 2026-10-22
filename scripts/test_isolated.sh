#!/usr/bin/env bash
# Полный прогон тестов бэкенда в отдельном compose-проекте: можно запускать
# параллельно из нескольких git worktree (имена контейнеров не пересекаются).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
[[ -f .env ]] || cp .env.example .env
project="t$(pwd | md5sum | cut -c1-10)"
docker compose -p "$project" --profile test run --rm --build api-test
rc=$?
docker compose -p "$project" --profile test down -v --remove-orphans >/dev/null 2>&1
exit $rc
