# ChessDep

Онлайн-шахматы (PvP) с элементами казино: деп фигур, скины, кейсы, апгрейд.

## Требования

- Linux
- Docker + Docker Compose v2

## Запуск

```bash
cp .env.example .env
make up
```

Открыть: `http://localhost:8080`

## Проверка тестов

```bash
make test
```

## Назначение администратора

```bash
make make-admin LOGIN=nik
```

## Доступ с другой машины

Добавьте origin этой машины (например `http://192.168.1.10:8080`) в `ALLOWED_ORIGINS` в `.env` через запятую и перезапустите `make up`.
