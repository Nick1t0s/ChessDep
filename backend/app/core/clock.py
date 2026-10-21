from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)
