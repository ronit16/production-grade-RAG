"""User management endpoints (list, create, role change, deactivate)."""
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.security import hash_password
from app.middleware.auth import AuthedContext
from app.models.db import User
from app.schemas.user import (
    RoleChangeRequest,
    UserActionResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserListItem,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserListItem])
async def list_users(ctx: AuthedContext, db: DBSession):
    """List all active users in the current tenant (owner/admin only)."""
    ctx.require_role("owner", "admin")
    result = await db.execute(
        select(User)
        .where(User.tenant_id == ctx.tenant_id, User.is_active == True)
        .order_by(User.created_at.asc())
    )
    users = result.scalars().all()
    return [
        UserListItem(
            user_id=str(u.id),
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login=u.last_login.isoformat() if u.last_login else None,
        )
        for u in users
    ]


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(req: UserCreateRequest, ctx: AuthedContext, db: DBSession):
    """Create a new member in the current tenant (owner/admin only)."""
    ctx.require_role("owner", "admin")

    if req.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot create a second owner")
    if req.role == "admin" and ctx.user_role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can create admin users")
    if req.role not in ("admin", "member"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be 'admin' or 'member'")

    if (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    if (await db.execute(select(User).where(User.username == req.username))).scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already taken")

    user = User(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        username=req.username,
        email=req.email,
        role=req.role,
        hashed_password=hash_password(req.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    return UserCreateResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        tenant_id=str(ctx.tenant_id),
    )


@router.patch("/{user_id}/role", response_model=UserActionResponse)
async def change_user_role(user_id: uuid.UUID, req: RoleChangeRequest, ctx: AuthedContext, db: DBSession):
    """Change a user's role (owner only)."""
    ctx.require_role("owner")

    if req.role not in ("admin", "member"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be 'admin' or 'member'")

    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change the owner's role")

    user.role = req.role
    await db.commit()
    return UserActionResponse(user_id=str(user_id), success=True)


@router.delete("/{user_id}", response_model=UserActionResponse)
async def deactivate_user(user_id: uuid.UUID, ctx: AuthedContext, db: DBSession):
    """Deactivate a user (owner only). Cannot deactivate self or the owner."""
    ctx.require_role("owner")

    if user_id == ctx.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot deactivate yourself")

    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == ctx.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot deactivate the owner")

    user.is_active = False
    await db.commit()
    return UserActionResponse(user_id=str(user_id), success=True)
