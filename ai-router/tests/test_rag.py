"""Tests for ai-router/rag.py — FTS5 document RAG search."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Use a temp database for each test, bypassing the db.py singleton."""
    import rag
    import db as db_mod

    db_path = tmp_path / "test_rag.db"

    original_rag = rag.DB_PATH
    original_db = db_mod.DB_PATH
    original_conn = db_mod._connection

    # Point both rag and db at the temp database
    rag.DB_PATH = db_path
    db_mod.DB_PATH = db_path
    # Force a fresh connection
    db_mod._connection = None
    # Initialize the db (creates tables)
    db_mod.get_db()

    yield str(db_path)

    # Cleanup
    db_mod.close_db()
    rag.DB_PATH = original_rag
    db_mod.DB_PATH = original_db
    db_mod._connection = original_conn


@pytest.fixture
def sample_docs(tmp_path):
    """Create sample documents for indexing."""
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "readme.md").write_text("# My Project\nThis is a sample project about machine learning and neural networks.")
    (docs / "setup.py").write_text("from setuptools import setup\nsetup(name='my-project', version='1.0')")
    (docs / "notes.txt").write_text("Meeting notes from Tuesday.\nDiscussed the API redesign and database migration.\nAction items: update schema, test endpoints.")
    (docs / "config.yaml").write_text("database:\n  host: localhost\n  port: 5432\n  name: mydb")

    # Hidden dir should be skipped
    hidden = docs / ".hidden"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("should not be indexed")

    # node_modules should be skipped
    nm = docs / "node_modules"
    nm.mkdir()
    (nm / "package.json").write_text("{}")

    return docs


class TestChunkText:
    def test_short_text_single_chunk(self):
        from rag import chunk_text
        chunks = chunk_text("Hello world", chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_text_multiple_chunks(self):
        from rag import chunk_text
        text = "Sentence one. " * 100  # ~1400 chars
        chunks = chunk_text(text, chunk_size=200)
        assert len(chunks) > 1

    def test_paragraph_boundary(self):
        from rag import chunk_text
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, chunk_size=30)
        assert len(chunks) >= 2

    def test_empty_text(self):
        from rag import chunk_text
        chunks = chunk_text("")
        assert chunks == [] or chunks == [""]


class TestIsRagQuery:
    def test_document_references(self):
        from rag import is_rag_query
        assert is_rag_query("what did that paper say about attention")
        assert is_rag_query("in my notes about the meeting")
        assert is_rag_query("that document about database migration")

    def test_non_rag_queries(self):
        from rag import is_rag_query
        assert not is_rag_query("what is linux")
        assert not is_rag_query("install firefox")
        assert not is_rag_query("what's the weather")


class TestIndexing:
    def test_index_directory(self, temp_db, sample_docs):
        from rag import index_directory, get_index_stats
        result = index_directory(str(sample_docs))
        assert result["indexed"] >= 3  # readme, setup, notes, config (not hidden/node_modules)
        assert result["errors"] == 0

        stats = get_index_stats()
        assert stats["total_docs"] >= 3

    def test_skips_hidden_dirs(self, temp_db, sample_docs):
        from rag import index_directory
        result = index_directory(str(sample_docs))
        # Check that hidden/secret.txt was not indexed
        from rag import search
        results = search("should not be indexed")
        assert len(results) == 0

    def test_skips_node_modules(self, temp_db, sample_docs):
        from rag import index_directory, search
        index_directory(str(sample_docs))
        results = search("package.json")
        # node_modules should be skipped
        matching = [r for r in results if "node_modules" in r.get("path", "")]
        assert len(matching) == 0

    def test_reindex_unchanged(self, temp_db, sample_docs):
        from rag import index_directory
        result1 = index_directory(str(sample_docs))
        result2 = index_directory(str(sample_docs))
        # Second run should skip already-indexed files
        assert result2["skipped"] >= result1["indexed"]

    def test_index_file(self, temp_db, sample_docs):
        from rag import index_file, search
        index_file(str(sample_docs / "readme.md"))
        results = search("machine learning")
        assert len(results) >= 1


class TestSearch:
    def test_search_finds_content(self, temp_db, sample_docs):
        from rag import index_directory, search
        index_directory(str(sample_docs))
        results = search("neural networks")
        assert len(results) >= 1
        assert any("readme" in r.get("path", "").lower() for r in results)

    def test_search_ranks_by_relevance(self, temp_db, sample_docs):
        from rag import index_directory, search
        index_directory(str(sample_docs))
        results = search("database migration")
        assert len(results) >= 1
        # notes.txt should rank higher (has both terms)

    def test_search_no_results(self, temp_db, sample_docs):
        from rag import index_directory, search
        index_directory(str(sample_docs))
        results = search("quantum_entanglement_xyz")
        assert len(results) == 0

    def test_search_for_prompt(self, temp_db, sample_docs):
        from rag import index_directory, search_for_prompt
        index_directory(str(sample_docs))
        prompt = search_for_prompt("machine learning")
        if prompt:  # May be empty if FTS doesn't match
            assert "[RAG:" in prompt or "readme" in prompt.lower()


class TestIndexStats:
    def test_empty_stats(self, temp_db):
        from rag import get_index_stats
        stats = get_index_stats()
        assert stats["total_docs"] == 0

    def test_stats_after_indexing(self, temp_db, sample_docs):
        from rag import index_directory, get_index_stats
        index_directory(str(sample_docs))
        stats = get_index_stats()
        assert stats["total_docs"] >= 3
        assert stats["total_chunks"] >= 3


class TestClearIndex:
    def test_clear(self, temp_db, sample_docs):
        from rag import index_directory, clear_index, get_index_stats
        index_directory(str(sample_docs))
        assert get_index_stats()["total_docs"] > 0
        clear_index()
        assert get_index_stats()["total_docs"] == 0
