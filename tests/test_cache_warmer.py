"""Tests for the cache warmer utility."""

from __future__ import annotations

import pathlib

import pytest
from obstore.store import MemoryStore

from brokenspoke_analyzer.core import datastore


class DummyContent:
    def __init__(self) -> None:
        self._chunks = [b"hello", RuntimeError("stream failed")]

    async def iter_chunked(self, _size: int):
        for chunk in self._chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class DummyResponse:
    def __init__(self) -> None:
        self.content = DummyContent()

    async def __aenter__(self) -> DummyResponse:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None


class DummySession:
    def get(self, _url: str) -> DummyResponse:
        return DummyResponse()


@pytest.mark.asyncio
async def test_fetch_to_cache_removes_partial_object(tmp_path: pathlib.Path) -> None:
    bna_store = datastore.BNADataStore(tmp_path, datastore.CacheType.USER_CACHE)
    bna_store.cache = MemoryStore()
    session = DummySession()

    with pytest.raises(RuntimeError, match="stream failed"):
        await bna_store.fetch_to_cache(
            session,
            "https://example.com/test.txt",
            "census/test.txt",
        )

    assert not bna_store.is_cached("census/test.txt")
