import argparse
import asyncio
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AdminAudit, User


async def make_admin(login: str) -> bool:
    async with SessionLocal() as db:
        async with db.begin():
            user = await db.scalar(select(User).where(User.login == login))
            if user is None:
                return False
            user.role = "admin"
            db.add(
                AdminAudit(
                    admin_id=None,
                    action="cli_make_admin",
                    target=login,
                )
            )
    return True


async def revoke_admin(login: str) -> bool:
    async with SessionLocal() as db:
        async with db.begin():
            user = await db.scalar(select(User).where(User.login == login))
            if user is None:
                return False
            user.role = "user"
            db.add(
                AdminAudit(
                    admin_id=None,
                    action="cli_revoke_admin",
                    target=login,
                )
            )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("make-admin").add_argument("login")
    sub.add_parser("revoke-admin").add_argument("login")
    args = parser.parse_args(argv)

    if args.command == "make-admin":
        ok = asyncio.run(make_admin(args.login))
    elif args.command == "revoke-admin":
        ok = asyncio.run(revoke_admin(args.login))
    else:  # pragma: no cover
        return 2

    if not ok:
        print("Пользователь не найден", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
