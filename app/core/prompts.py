"""
Prompt configuration — loads config/prompts.yaml once at startup.

Mirrors the get_settings() pattern: @lru_cache singleton, frozen dataclass,
env-override escape hatch (PROMPTS_PATH) for tests and A/B experiments.

Usage:
    from app.core.prompts import get_prompts
    p = get_prompts()
    text = p.rag_context_chunk.format(idx=1, section="intro", page=3, text="...")
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "prompts.yaml"


@dataclass(frozen=True)
class Prompts:
    version: str
    # rag section
    rag_system: str
    rag_context_chunk: str          # use .format(idx, section, page, text)
    rag_fallback_answer: str
    # retriever section
    retriever_query_rewrite: str
    # evaluator section
    evaluator_ca_system: str
    evaluator_ca_user: str          # use .format(history, question, answer)


def _load(path: Path) -> Prompts:
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    rag = raw["rag"]
    ret = raw["retriever"]
    evl = raw["evaluator"]
    return Prompts(
        version=raw.get("version", "0.0.0"),
        rag_system=rag["system"].strip(),
        rag_context_chunk=rag["context_chunk"],
        rag_fallback_answer=rag["fallback_answer"].strip(),
        retriever_query_rewrite=ret["query_rewrite"].strip(),
        evaluator_ca_system=evl["context_awareness_system"].strip(),
        evaluator_ca_user=evl["context_awareness_user"],
    )


@lru_cache(maxsize=1)
def get_prompts() -> Prompts:
    """
    Cached singleton. Respects PROMPTS_PATH env override so tests can inject
    an alternate YAML without monkey-patching module globals.
    """
    path_str = os.environ.get("PROMPTS_PATH", "")
    path = Path(path_str) if path_str else _DEFAULT_PATH
    return _load(path)
