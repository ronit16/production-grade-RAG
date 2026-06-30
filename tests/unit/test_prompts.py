"""
Unit tests for the prompt YAML config loader (app/core/prompts.py).

All tests run without containers or network — just filesystem + lru_cache.
"""
import os
import textwrap
from pathlib import Path

import pytest

from app.core.prompts import Prompts, _load, get_prompts


# ─── helpers ──────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "prompts.yaml"
    p.write_text(textwrap.dedent(content))
    return p


MINIMAL_YAML = """\
    version: "2.0.0"
    rag:
      system: |
        System prompt.
      context_chunk: |
        Chunk {idx} {section} {page} {text}
      fallback_answer: Fallback.
    retriever:
      query_rewrite: |
        Rewrite this.
    evaluator:
      context_awareness_system: |
        Judge this.
      context_awareness_user: |
        H:{history} Q:{question} A:{answer}
"""


# ─── 1. _load() ───────────────────────────────────────────────────────────────

class TestLoad:
    def test_returns_prompts_dataclass(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        p = _load(path)
        assert isinstance(p, Prompts)

    def test_version_parsed(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        p = _load(path)
        assert p.version == "2.0.0"

    def test_rag_system_stripped(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        p = _load(path)
        assert p.rag_system == "System prompt."

    def test_context_chunk_format_placeholders(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        p = _load(path)
        result = p.rag_context_chunk.format(idx=1, section="intro", page=3, text="hello")
        assert "1" in result
        assert "intro" in result
        assert "3" in result
        assert "hello" in result

    def test_evaluator_ca_user_format_placeholders(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        p = _load(path)
        result = p.evaluator_ca_user.format(history="h", question="q", answer="a")
        assert "h" in result and "q" in result and "a" in result

    def test_frozen_dataclass_is_immutable(self, tmp_path):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        p = _load(path)
        with pytest.raises((AttributeError, TypeError)):
            p.rag_system = "mutated"  # type: ignore[misc]


# ─── 2. get_prompts() singleton ───────────────────────────────────────────────

class TestGetPrompts:
    def test_returns_prompts_from_default_yaml(self):
        p = get_prompts()
        assert isinstance(p, Prompts)
        assert p.version  # non-empty version string

    def test_cache_returns_same_object(self):
        p1 = get_prompts()
        p2 = get_prompts()
        assert p1 is p2

    def test_env_override_loads_alternate_file(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, MINIMAL_YAML)
        # Clear the lru_cache so the env override is respected
        get_prompts.cache_clear()
        monkeypatch.setenv("PROMPTS_PATH", str(path))
        try:
            p = get_prompts()
            assert p.version == "2.0.0"
            assert p.rag_system == "System prompt."
        finally:
            get_prompts.cache_clear()
            monkeypatch.delenv("PROMPTS_PATH", raising=False)
            # Reload from default so subsequent tests use the real file
            get_prompts()


# ─── 3. Production prompts.yaml sanity checks ─────────────────────────────────

class TestProductionPrompts:
    def test_rag_system_mentions_context_and_citations(self):
        p = get_prompts()
        assert "context" in p.rag_system.lower()
        assert "[1]" in p.rag_system or "cite" in p.rag_system.lower()

    def test_context_chunk_has_all_required_placeholders(self):
        p = get_prompts()
        rendered = p.rag_context_chunk.format(idx=1, section="s", page=2, text="t")
        for token in ("1", "s", "2", "t"):
            assert token in rendered

    def test_query_rewrite_instructs_self_contained(self):
        p = get_prompts()
        assert "self-contained" in p.retriever_query_rewrite.lower() or \
               "self contained" in p.retriever_query_rewrite.lower()

    def test_evaluator_ca_user_has_all_placeholders(self):
        p = get_prompts()
        rendered = p.evaluator_ca_user.format(history="H", question="Q", answer="A")
        for token in ("H", "Q", "A"):
            assert token in rendered
