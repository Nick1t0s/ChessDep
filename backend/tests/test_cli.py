from sqlalchemy import select

from app.cli import make_admin
from app.models import AdminAudit, User
from tests.conftest import register


async def test_make_admin(client, db) -> None:
    resp = await register(client, login="bob")
    assert resp.status_code == 201

    assert await make_admin("bob") is True

    async with db.begin():
        user = await db.scalar(select(User).where(User.login == "bob"))
        audits = (await db.scalars(select(AdminAudit))).all()
    assert user is not None
    assert user.role == "admin"
    assert len(audits) == 1
    assert audits[0].action == "cli_make_admin"
    assert audits[0].target == "bob"
    assert audits[0].admin_id is None
