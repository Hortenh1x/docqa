"""Admin CLI — the whole "admin panel" of v1.

Usage:
    python -m app.cli create-tenant --name acme
    python -m app.cli create-key --tenant-id <uuid> [--name ci]
    python -m app.cli revoke-key --prefix <8 chars>
    python -m app.cli list-tenants
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import display_key, generate_api_key
from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import ApiKey, Tenant


async def create_tenant(name: str) -> None:
    async with get_sessionmaker()() as session:
        tenant = Tenant(name=name)
        session.add(tenant)
        await session.commit()
        print(f"tenant created: id={tenant.id} name={tenant.name!r}")


async def create_key(tenant_id: uuid.UUID, name: str) -> None:
    async with get_sessionmaker()() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            print(f"error: tenant {tenant_id} not found", file=sys.stderr)
            raise SystemExit(1)
        plaintext, prefix, key_hash = generate_api_key()
        session.add(ApiKey(tenant_id=tenant_id, prefix=prefix, key_hash=key_hash, name=name))
        await session.commit()
        print(f"api key created for tenant {tenant.name!r} (key name: {name!r})")
        print(f"  {plaintext}")
        print("store it now — the key is shown only once and cannot be recovered")


async def revoke_key(prefix: str) -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None))
        )
        keys = result.scalars().all()
        if not keys:
            print(f"error: no active key with prefix {prefix!r}", file=sys.stderr)
            raise SystemExit(1)
        for key in keys:
            key.revoked_at = datetime.now(UTC)
        await session.commit()
        for key in keys:
            print(f"revoked {display_key(key.prefix)} (id={key.id})")


async def list_tenants() -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Tenant).order_by(Tenant.created_at))
        rows = result.scalars().all()
        if not rows:
            print("no tenants")
            return
        for t in rows:
            state = "active" if t.is_active else "inactive"
            print(f"{t.id}  {state:8}  {t.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DocQA admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-tenant", help="create a tenant")
    p.add_argument("--name", required=True)

    p = sub.add_parser("create-key", help="create an API key (printed once)")
    p.add_argument("--tenant-id", required=True, type=uuid.UUID)
    p.add_argument("--name", default="default")

    p = sub.add_parser("revoke-key", help="revoke an API key by its 8-char prefix")
    p.add_argument("--prefix", required=True)

    sub.add_parser("list-tenants", help="list tenants")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    async def run() -> None:
        try:
            if args.command == "create-tenant":
                await create_tenant(args.name)
            elif args.command == "create-key":
                await create_key(args.tenant_id, args.name)
            elif args.command == "revoke-key":
                await revoke_key(args.prefix)
            elif args.command == "list-tenants":
                await list_tenants()
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
