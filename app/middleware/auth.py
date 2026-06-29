"""
Production RAG System - Auth Middleware & Tenant Context
Injects tenant + user context into every request. Enforces plan limits.
"""
import hashlib
import ipaddress
import json
import time
from dataclasses import dataclass, field
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


@dataclass
class _TenantStub:
    """Minimal Tenant-like object rebuilt from the Redis JSON cache.
    Avoids pickle so a poisoned cache key cannot execute arbitrary code."""
    id: UUID
    slug: str
    vector_namespace: str
    plan: PlanTier
    llm_config: dict = field(default_factory=dict)
    rag_config: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    is_active: bool = True


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
        data = json.loads(cached)
        tenant: Tenant | _TenantStub = _TenantStub(
            id=UUID(data["id"]),
            slug=data["slug"],
            vector_namespace=data["vector_namespace"],
            plan=PlanTier(data["plan"]),
            llm_config=data.get("llm_config") or {},
            rag_config=data.get("rag_config") or {},
            features=data.get("features") or {},
        )
    else:
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not found or inactive")
        await redis.setex(cache_key, _TENANT_CACHE_TTL, json.dumps({
            "id": str(tenant.id),
            "slug": tenant.slug,
            "vector_namespace": tenant.vector_namespace,
            "plan": tenant.plan.value,
            "llm_config": tenant.llm_config or {},
            "rag_config": tenant.rag_config or {},
            "features": tenant.features or {},
        }))

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
    if settings.APP_ENV == "test":
        return ctx

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
# Login / register rate limiter (IP-based, no auth required)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_client_ip(request: Request) -> str:
    """Return the real client IP, trusting X-Forwarded-For only from known proxies.

    Blindly reading X-Forwarded-For is a bypass vector: any client can spoof it.
    We only parse it when the direct TCP peer is in TRUSTED_PROXY_CIDRS.
    When trusted, we walk right-to-left and return the first hop that is NOT itself
    a trusted proxy — this gives the originating client IP even through proxy chains.
    """
    peer_ip = request.client.host if request.client else None
    if not peer_ip:
        return "unknown"

    trusted_cidrs = settings.TRUSTED_PROXY_CIDRS
    if not trusted_cidrs:
        return peer_ip  # no proxies configured — use the direct peer

    try:
        peer_addr = ipaddress.ip_address(peer_ip)
        peer_is_trusted = any(
            peer_addr in ipaddress.ip_network(cidr, strict=False)
            for cidr in trusted_cidrs
        )
    except ValueError:
        return peer_ip  # unparseable peer IP — fall back to peer

    if not peer_is_trusted:
        return peer_ip  # direct connection from untrusted peer

    # Peer is a trusted proxy — walk X-Forwarded-For right-to-left
    xff = request.headers.get("X-Forwarded-For", "")
    if not xff:
        return peer_ip

    for hop in reversed([h.strip() for h in xff.split(",")]):
        try:
            hop_addr = ipaddress.ip_address(hop)
            if not any(hop_addr in ipaddress.ip_network(c, strict=False) for c in trusted_cidrs):
                return hop  # first untrusted hop is the real client
        except ValueError:
            continue

    return peer_ip  # all hops were trusted proxies — use peer as fallback


async def check_login_rate_limit(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    """IP-based rate limiter for unauthenticated endpoints (login, register).

    Limits to LOGIN_RATE_LIMIT_PER_MINUTE attempts per IP per 60-second window.
    Skipped in test/development environments.
    """
    if settings.APP_ENV in ("test", "development"):
        return

    ip = _resolve_client_ip(request)
    key = f"login_attempt:{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.LOGIN_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Retry in 60 seconds.",
            headers={"Retry-After": "60"},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Convenience type aliases
# ─────────────────────────────────────────────────────────────────────────────

AuthedContext  = Annotated[TenantContext, Depends(get_tenant_ctx)]
RatedContext   = Annotated[TenantContext, Depends(check_rate_limit)]
