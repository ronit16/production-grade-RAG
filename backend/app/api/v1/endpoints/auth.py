"""Authentication endpoints — register and login."""
import time
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.db import PlanTier, Tenant, User

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TOKEN_TTL = 60 * 60 * 24  # 24 h


# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    email: str


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

    slug = req.email.split("@")[0] + "-" + str(uuid.uuid4())[:8]
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        name=req.email.split("@")[0],
        plan=PlanTier.FREE,
        vector_namespace=slug,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=req.email,
        role="owner",
        hashed_password=pwd_context.hash(req.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    return AuthResponse(
        access_token=_issue_token(user),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        email=user.email,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password and receive a JWT."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not pwd_context.verify(req.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    return AuthResponse(
        access_token=_issue_token(user),
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
    )
