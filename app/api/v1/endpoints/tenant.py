"""Tenant info and usage stats endpoint."""
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.middleware.auth import AuthedContext
from app.models.db import Document, Session, Tenant, UsageLog, User
from app.schemas.user import PlanLimits, TenantInfo, TenantInfoResponse, TenantUsage

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantInfoResponse)
async def get_tenant_info(ctx: AuthedContext, db: DBSession):
    """Return tenant metadata, plan limits, and today's usage stats."""
    today = datetime.now(timezone.utc).date()

    doc_count = (await db.execute(
        select(func.count(Document.id)).where(
            Document.tenant_id == ctx.tenant_id,
            Document.deleted_at.is_(None),
        )
    )).scalar() or 0

    session_count = (await db.execute(
        select(func.count(Session.id)).where(
            Session.tenant_id == ctx.tenant_id,
            Session.is_active == True,
        )
    )).scalar() or 0

    member_count = (await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == ctx.tenant_id,
            User.is_active == True,
        )
    )).scalar() or 0

    usage_row = (await db.execute(
        select(UsageLog).where(
            UsageLog.tenant_id == ctx.tenant_id,
            func.date(UsageLog.date) == today,
        )
    )).scalar_one_or_none()
    tokens_today = (usage_row.tokens_in + usage_row.tokens_out) if usage_row else 0
    queries_today = usage_row.query_count if usage_row else 0

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == ctx.tenant_id)
    )).scalar_one()

    return TenantInfoResponse(
        tenant=TenantInfo(
            tenant_id=str(tenant.id),
            slug=tenant.slug,
            name=tenant.name,
            plan=tenant.plan.value,
            is_active=tenant.is_active,
            created_at=tenant.created_at.isoformat() if tenant.created_at else None,
        ),
        limits=PlanLimits(**ctx.limits),
        usage=TenantUsage(
            doc_count=doc_count,
            session_count=session_count,
            tokens_today=tokens_today,
            query_count_today=queries_today,
        ),
        member_count=member_count,
    )
