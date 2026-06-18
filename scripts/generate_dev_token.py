"""
Dev utility: seeds a test tenant + user into the DB and prints a ready-to-use JWT.

Usage (inside the api container):
    docker compose exec api python scripts/generate_dev_token.py

Usage (locally from project root):
    PYTHONPATH=. python3 scripts/generate_dev_token.py
"""
import sys
import os
# Ensure project root is on sys.path regardless of how the script is invoked
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import time
import uuid

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import get_settings
from app.models.db import Tenant, User, PlanTier

settings = get_settings()

TENANT_SLUG = "dev-tenant"
USER_EMAIL  = "dev@example.com"
TOKEN_TTL   = 86400  # 24 hours


async def seed_and_generate() -> str:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Upsert tenant
        result = await db.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        tenant = result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=uuid.uuid4(),
                slug=TENANT_SLUG,
                name="Dev Tenant",
                plan=PlanTier.FREE,
                vector_namespace=TENANT_SLUG,
                is_active=True,
            )
            db.add(tenant)
            await db.commit()
            await db.refresh(tenant)
            print(f"Created tenant: {tenant.id}")
        else:
            print(f"Using existing tenant: {tenant.id}")

        # Upsert user
        result = await db.execute(select(User).where(User.email == USER_EMAIL))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                email=USER_EMAIL,
                role="owner",
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"Created user: {user.id}")
        else:
            print(f"Using existing user: {user.id}")

    await engine.dispose()

    # Sign JWT with private key
    with open(settings.JWT_PRIVATE_KEY_PATH) as f:
        private_key = f.read()

    payload = {
        "sub":       str(user.id),
        "tenant_id": str(tenant.id),
        "role":      "owner",
        "exp":       int(time.time()) + TOKEN_TTL,
        "iat":       int(time.time()),
    }
    token = jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)
    return token


if __name__ == "__main__":
    token = asyncio.run(seed_and_generate())
    print("\n" + "="*60)
    print("Bearer token (valid 24h):")
    print("="*60)
    print(token)
    print("="*60)
    print("\nSwagger UI: paste into Authorize → Bearer <token>")
    print('curl:  -H "Authorization: Bearer ' + token[:40] + '..."')
