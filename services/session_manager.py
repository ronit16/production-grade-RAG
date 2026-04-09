import json
from uuid import UUID
from core.database import redis_client

SESSION_EXPIRY = 3600 # 1 hour

def _session_key(session_id: UUID, tenant_id: str) -> str:
    return f"tenant:{tenant_id}:session:{session_id}:history"

async def get_session_history_from_redis(session_id: UUID, tenant_id: str) -> str:
    history_json = await redis_client.get(_session_key(session_id, tenant_id))
    if history_json:
        messages = json.loads(history_json)
        formatted_history = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages])
        return formatted_history
    return ""

async def append_to_redis_session(session_id: UUID, tenant_id: str, role: str, content: str):
    key = _session_key(session_id, tenant_id)
    history_json = await redis_client.get(key)

    if history_json:
        messages = json.loads(history_json)
    else:
        messages = []

    messages.append({"role": role, "content": content})

    # Keep last 10 messages for context
    if len(messages) > 10:
        messages = messages[-10:]

    await redis_client.setex(key, SESSION_EXPIRY, json.dumps(messages))

async def clear_redis_session(session_id: UUID, tenant_id: str):
    await redis_client.delete(_session_key(session_id, tenant_id))
