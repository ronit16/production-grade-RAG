"""Authentication endpoints — register and login."""
import time
import uuid

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import PlanTier, Tenant, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

TOKEN_TTL = 60 * 60 * 24  # 24 h


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
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    # Check username uniqueness
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
        hashed_password=_hash_password(req.password),
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
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password and receive a JWT."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not _verify_password(req.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    return AuthResponse(
        access_token=_issue_token(user),
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        username=user.username or user.email.split("@")[0],
    )
