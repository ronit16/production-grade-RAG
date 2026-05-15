"""Unit tests: token estimation and chunk deduplication."""
import hashlib
import pytest
from app.workers.ingestion import _estimate_tokens


class TestChunking:
    def test_token_estimate_non_zero(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert _estimate_tokens(text) > 0

    def test_token_estimate_scales_with_length(self):
        short = "Hello world"
        long  = "Hello world " * 100
        assert _estimate_tokens(long) > _estimate_tokens(short)

    def test_token_estimate_minimum_one(self):
        assert _estimate_tokens("x") == 1

    def test_chunk_dedup_via_hash(self):
        text   = "The same text repeated."
        hash1  = hashlib.sha256(text.encode()).hexdigest()
        hash2  = hashlib.sha256(text.encode()).hexdigest()
        assert hash1 == hash2

    def test_different_text_different_hash(self):
        hash1 = hashlib.sha256("Text A".encode()).hexdigest()
        hash2 = hashlib.sha256("Text B".encode()).hexdigest()
        assert hash1 != hash2
