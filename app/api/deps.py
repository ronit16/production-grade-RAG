"""
Shared FastAPI dependency type aliases.
Import these in endpoint modules instead of spelling out Depends() each time.
"""
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_redis

DBSession   = Annotated[AsyncSession,   Depends(get_db)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
