"""
Production RAG System - Auth Middleware & Tenant Context
Injects tenant + user context into every request. Enforces plan limits.
"""
import hashlib
import time
from typing import Annotated, Optional
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.models.db import APIKey, Tenant, User, PlanTier, PLAN_LIMITS
from app.core.database import get_db, get_redis

settings = get_settings()
security = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────────────────────
# Tenant context (attached to request.state)
# ─────────────────────────────────────────────────────────────────────────────

class TenantContext:
    __slots__ = (
        "tenant_id", "tenant_slug", "vector_namespace",
        "user_id", "user_role", "plan", "limits",
        "llm_config", "rag_config", "features",
    )

    def __init__(
        self,
        tenant: Tenant,
        user_id: Optional[UUID] = None,
        user_role: str = "member",
    ):
        self.tenant_id        = tenant.id
        self.tenant_slug      = tenant.slug
        self.vector_namespace = tenant.vector_namespace
        self.user_id          = user_id
        self.user_role        = user_role
        self.plan             = tenant.plan
        self.limits           = PLAN_LIMITS[tenant.plan]
        self.llm_config       = tenant.llm_config or {}
        self.rag_config       = tenant.rag_config or {}
        self.features         = tenant.features or {}

    def require_role(self, *roles: str) -> None:
        if self.user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{self.user_role}' not permitted. Required: {roles}",
            )

    def check_feature(self, flag: str) -> bool:
        return self.features.get(flag, False)


# ─────────────────────────────────────────────────────────────────────────────
# JWT helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_public_key() -> str:
    with open(settings.JWT_PUBLIC_KEY_PATH) as f:
        return f.read()


def decode_jwt(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            _load_public_key(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "tenant_id", "role"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def _resolve_api_key(
    raw_key: str,
    db: AsyncSession,
) -> Optional[tuple[Tenant, str]]:
    """Look up an API key, return (tenant_id, scopes) or None."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        .join(Tenant, APIKey.tenant_id == Tenant.id)
        .where(Tenant.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        return None
    return api_key.tenant_id, api_key.scopes


# ─────────────────────────────────────────────────────────────────────────────
# Core dependency: get_tenant_ctx
# ─────────────────────────────────────────────────────────────────────────────

_TENANT_CACHE_TTL = 60   # seconds


async def get_tenant_ctx(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TenantContext:
    """
    FastAPI dependency injected into every protected route.
    Accepts: Bearer JWT  or  Bearer sk_<api_key>
    Attaches TenantContext to request.state.tenant
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user_id: Optional[UUID] = None
    role: str = "member"

    if token.startswith("sk_"):
        # ── API Key auth ────────────────────────────────────────────────────
        result = await _resolve_api_key(token, db)
        if not result:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        tenant_id, scopes = result
        role = "api"  # API keys get a synthetic role
    else:
        # ── JWT auth ────────────────────────────────────────────────────────
        payload   = decode_jwt(token)
        tenant_id = UUID(payload["tenant_id"])
        user_id   = UUID(payload["sub"])
        role      = payload["role"]

    # ── Load tenant (Redis cache → DB) ────────────────────────────────────
    cache_key  = f"tenant:{tenant_id}"
    cached     = await redis.get(cache_key)

    if cached:
        import pickle
        tenant = pickle.loads(cached)
    else:
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not found or inactive")
        import pickle
        await redis.setex(cache_key, _TENANT_CACHE_TTL, pickle.dumps(tenant))

    ctx = TenantContext(tenant=tenant, user_id=user_id, user_role=role)
    request.state.tenant = ctx
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiting dependency
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


async def check_rate_limit(
    ctx: TenantContext = Depends(get_tenant_ctx),
    redis: aioredis.Redis = Depends(get_redis),
) -> TenantContext:
    """Token-bucket rate limiting per tenant using Redis."""
    rps   = ctx.limits["rps"]
    key   = f"ratelimit:{ctx.tenant_id}:tokens"
    refill_key = f"ratelimit:{ctx.tenant_id}:last"
    now   = time.time()

    async with redis.pipeline(transaction=True) as pipe:
        await pipe.get(key)
        await pipe.get(refill_key)
        tokens_raw, last_raw = await pipe.execute()

    tokens = float(tokens_raw) if tokens_raw else float(rps)
    last   = float(last_raw)   if last_raw   else now

    # Refill
    elapsed = now - last
    tokens  = min(rps, tokens + elapsed * rps)

    if tokens < 1:
        retry_after = int((1 - tokens) / rps)
        raise RateLimitExceeded(retry_after)

    async with redis.pipeline(transaction=True) as pipe:
        await pipe.set(key, tokens - 1, ex=60)
        await pipe.set(refill_key, now, ex=60)
        await pipe.execute()

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Convenience type aliases
# ─────────────────────────────────────────────────────────────────────────────

AuthedContext  = Annotated[TenantContext, Depends(get_tenant_ctx)]
RatedContext   = Annotated[TenantContext, Depends(check_rate_limit)]
