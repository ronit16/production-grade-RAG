from typing import Optional
from pydantic import BaseModel


class UserListItem(BaseModel):
    user_id: str
    username: Optional[str]
    email: str
    role: str
    is_active: bool
    created_at: Optional[str]
    last_login: Optional[str]


class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "member"


class UserCreateResponse(BaseModel):
    user_id: str
    username: str
    email: str
    role: str
    tenant_id: str


class RoleChangeRequest(BaseModel):
    role: str


class UserActionResponse(BaseModel):
    user_id: str
    success: bool


class TenantInfo(BaseModel):
    tenant_id: str
    slug: str
    name: str
    plan: str
    is_active: bool
    created_at: Optional[str]


class PlanLimits(BaseModel):
    max_docs: Optional[int]
    tokens_day: Optional[int]
    rps: int
    max_sessions: Optional[int]


class TenantUsage(BaseModel):
    doc_count: int
    session_count: int
    tokens_today: int
    query_count_today: int


class TenantInfoResponse(BaseModel):
    tenant: TenantInfo
    limits: PlanLimits
    usage: TenantUsage
    member_count: int
