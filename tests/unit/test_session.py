"""Unit tests: SessionState logic (no I/O required)."""
import time
import uuid
import pytest
from app.services.session import SessionState, Message, MAX_HISTORY_MESSAGES, MAX_HISTORY_TOKENS


def _make_state() -> SessionState:
    return SessionState(
        session_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        user_id=None,
        messages=[],
        created_at=time.time(),
        last_active=time.time(),
    )


class TestSessionState:
    def test_rolling_window_enforced(self):
        state = _make_state()
        for i in range(MAX_HISTORY_MESSAGES + 10):
            state.add_message(Message(role="user", content=f"Message {i}"))
        assert len(state.messages) == MAX_HISTORY_MESSAGES

    def test_get_history_respects_token_budget(self):
        state = _make_state()
        for i in range(50):
            state.messages.append(Message(role="user", content="x " * 200))  # ~50 tokens each

        history = state.get_history_for_prompt()
        total_tokens = sum(len(m["content"]) // 4 for m in history)
        assert total_tokens <= MAX_HISTORY_TOKENS

    def test_token_counters_updated_on_add(self):
        state = _make_state()
        state.add_message(Message(role="user", content="hello", tokens_in=10))
        assert state.total_tokens_in == 10

        state.add_message(Message(role="assistant", content="world", tokens_out=20))
        assert state.total_tokens_out == 20

    def test_last_active_updated_on_add(self):
        state = _make_state()
        before = state.last_active
        time.sleep(0.01)
        state.add_message(Message(role="user", content="hi"))
        assert state.last_active >= before
