"""Authentication endpoints — register, login, invite, register-member."""
import json
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.database import get_db, get_redis
from app.core.security import hash_password, verify_password
from app.middleware.auth import AuthedContext
from app.models.db import PlanTier, Tenant, User

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_TTL = 60 * 60 * 24  # 24 h
INVITE_TTL = 60 * 60 * 24 * 7  # 7 days


# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(v) > 32:
            raise ValueError("Username must be 32 characters or fewer")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, hyphens, and underscores")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    email: str
    username: str
    role: str


class InviteResponse(BaseModel):
    invite_code: str
    expires_at: str


class RegisterMemberRequest(BaseModel):
    invite_code: str
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(v) > 32:
            raise ValueError("Username must be 32 characters or fewer")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, hyphens, and underscores")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ── Helpers ──────────────────────────────────────────────────────────────────

def _issue_token(user: User) -> str:
    settings = get_settings()
    with open(settings.JWT_PRIVATE_KEY_PATH) as f:
        private_key = f.read()
    payload = {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role,
        "exp": int(time.time()) + TOKEN_TTL,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new account. Each user gets their own isolated tenant."""
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already taken")

    slug = req.username.lower() + "-" + str(uuid.uuid4())[:8]
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=req.username,
        plan=PlanTier.FREE,
        vector_namespace=slug,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username=req.username,
        email=req.email,
        role="owner",
        hashed_password=hash_password(req.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    return AuthResponse(
        access_token=_issue_token(user),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        email=user.email,
        username=user.username,
        role=user.role,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password and receive a JWT."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    return AuthResponse(
        access_token=_issue_token(user),
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        username=user.username or user.email.split("@")[0],
        role=user.role,
    )


@router.post("/invite", response_model=InviteResponse)
async def generate_invite(
    ctx: AuthedContext,
    redis: aioredis.Redis = Depends(get_redis),
):
    """Generate a single-use invite code for joining this tenant (owner/admin only)."""
    ctx.require_role("owner", "admin")
    code = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=INVITE_TTL)
    payload = json.dumps({
        "tenant_id": str(ctx.tenant_id),
        "created_by": str(ctx.user_id),
        "role": "member",
    })
    await redis.setex(f"invite:{code}", INVITE_TTL, payload)
    return InviteResponse(invite_code=code, expires_at=expires_at.isoformat())


@router.post("/register-member", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_member(
    req: RegisterMemberRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Register as a member of an existing tenant using an invite code."""
    raw = await redis.get(f"invite:{req.invite_code}")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired invite code")
    invite = json.loads(raw)
    tenant_id = uuid.UUID(invite["tenant_id"])

    t_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True)
    )
    tenant = t_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tenant no longer active")

    if (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    if (await db.execute(select(User).where(User.username == req.username))).scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already taken")

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=req.username,
        email=req.email,
        role=invite.get("role", "member"),
        hashed_password=hash_password(req.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    # Single-use: consume the invite code
    await redis.delete(f"invite:{req.invite_code}")

    return AuthResponse(
        access_token=_issue_token(user),
        user_id=str(user.id),
        tenant_id=str(tenant_id),
        email=user.email,
        username=user.username,
        role=user.role,
    )
