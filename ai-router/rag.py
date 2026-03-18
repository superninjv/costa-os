"""
FTS5-based document RAG search for Costa OS.

Uses SQLite FTS5 for zero-VRAM, zero-embedding document retrieval.
Documents are chunked and indexed into ~/.config/costa/costa.db.
"""

import sqlite3
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Database path
DB_PATH = Path.home() / ".config" / "costa" / "costa.db"

# Default file extensions to index
DEFAULT_EXTENSIONS = {
    ".md", ".txt", ".py", ".rs", ".js", ".ts", ".java", ".go",
    ".sh", ".yaml", ".yml", ".toml", ".json", ".conf", ".cfg",
}

# Directories to skip during recursive walk
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "target", "dist", "build",
}

# Patterns that indicate a query references personal documents
RAG_PATTERNS = [
    r"\bpaper\b",
    r"\bdocument\b",
    r"\bnotes?\b",
    r"\barticle\b",
    r"\breadme\b",
    r"\bthat file about\b",
    r"\bwhat did .+ say about\b",
    r"\bin my .*(notes|docs|files|documents)\b",
    r"\bfrom the (pdf|doc|file|text)\b",
    r"\bthat .*(paper|document|doc)\b",
    r"\bmy .*(paper|document|notes|article)\b",
]
_rag_re = re.compile("|".join(RAG_PATTERNS), re.IGNORECASE)


def get_db() -> sqlite3.Connection:
    """Get a connection to the Costa OS database."""
    try:
        from db import get_db as _get_db
        return _get_db()
    except ImportError:
        pass
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_tables(conn: sqlite3.Connection | None = None) -> None:
    """Create FTS5 and metadata tables if they don't exist."""
    if conn is None:
        conn = get_db()
    conn.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
            path, chunk_id, content,
            tokenize='porter unicode61'
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS document_meta (
            path TEXT PRIMARY KEY,
            indexed_at TEXT,
            chunk_count INTEGER,
            size_bytes INTEGER
        )"""
    )
    conn.commit()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks at sentence/paragraph boundaries.

    Tries to split on paragraph breaks (\\n\\n) first, then line breaks (\\n),
    then sentence endings ('. ') within the size limit.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
        return [text.strip()]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        if end < text_len:
            # Try to find a good break point within the chunk
            segment = text[start:end]
            break_pos = -1

            # Try paragraph break first
            pp_pos = segment.rfind("\n\n")
            if pp_pos > chunk_size // 4:
                break_pos = pp_pos + 2  # include the double newline

            # Try line break
            if break_pos == -1:
                nl_pos = segment.rfind("\n")
                if nl_pos > chunk_size // 4:
                    break_pos = nl_pos + 1

            # Try sentence boundary
            if break_pos == -1:
                sent_pos = segment.rfind(". ")
                if sent_pos > chunk_size // 4:
                    break_pos = sent_pos + 2

            if break_pos != -1:
                end = start + break_pos

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start forward with overlap
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def index_file(filepath: str | Path) -> bool:
    """Index a single file. Deletes old chunks first, then inserts new ones.

    Returns True on success, False on error.
    """
    filepath = Path(filepath).resolve()
    if not filepath.is_file():
        return False

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return False

    path_str = str(filepath)
    chunks = chunk_text(content)
    if not chunks:
        return False

    conn = get_db()
    ensure_tables(conn)
    try:
        # Delete old chunks for this file
        conn.execute("DELETE FROM documents WHERE path = ?", (path_str,))

        # Insert new chunks
        for i, chunk in enumerate(chunks):
            conn.execute(
                "INSERT INTO documents (path, chunk_id, content) VALUES (?, ?, ?)",
                (path_str, str(i), chunk),
            )

        # Update metadata
        now = datetime.now(timezone.utc).isoformat()
        size_bytes = filepath.stat().st_size
        conn.execute(
            """INSERT OR REPLACE INTO document_meta
               (path, indexed_at, chunk_count, size_bytes)
               VALUES (?, ?, ?, ?)""",
            (path_str, now, len(chunks), size_bytes),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False


def index_directory(
    directory: str | Path, extensions: set[str] | None = None
) -> dict:
    """Walk a directory recursively and index all matching files.

    Args:
        directory: Root directory to index.
        extensions: Set of file extensions to include (e.g. {'.md', '.py'}).
                    Defaults to DEFAULT_EXTENSIONS.

    Returns:
        {"indexed": int, "skipped": int, "errors": int}
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        return {"indexed": 0, "skipped": 0, "errors": 1}

    exts = extensions if extensions is not None else DEFAULT_EXTENSIONS
    result = {"indexed": 0, "skipped": 0, "errors": 0}

    conn = get_db()
    ensure_tables(conn)

    # Load existing metadata for skip-if-unchanged check
    meta = {}
    try:
        rows = conn.execute("SELECT path, indexed_at FROM document_meta").fetchall()
        for row in rows:
            meta[row["path"]] = row["indexed_at"]
    except Exception:
        pass
    # Do NOT close conn — it's the singleton from db.get_db()

    for root, dirs, files in os.walk(directory):
        # Skip hidden directories and known junk dirs
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in SKIP_DIRS
        ]

        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue

            path_str = str(fpath.resolve())

            # Check if file changed since last index
            try:
                mtime = datetime.fromtimestamp(
                    fpath.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                result["errors"] += 1
                continue

            indexed_at = meta.get(path_str)
            if indexed_at and indexed_at >= mtime:
                result["skipped"] += 1
                continue

            if index_file(fpath):
                result["indexed"] += 1
            else:
                result["errors"] += 1

    return result


def search(query: str, limit: int = 5) -> list[dict]:
    """Search indexed documents using FTS5 MATCH.

    Returns list of {path, chunk_id, content, rank} sorted by relevance.
    """
    if not query or not query.strip():
        return []

    conn = get_db()
    ensure_tables(conn)
    try:
        # Escape FTS5 special characters in the query for safety,
        # then wrap each token in double quotes so they're treated as literals.
        tokens = query.strip().split()
        safe_query = " ".join(f'"{t}"' for t in tokens if t)
        if not safe_query:
            return []

        rows = conn.execute(
            """SELECT path, chunk_id, content, bm25(documents) AS rank
               FROM documents
               WHERE documents MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (safe_query, limit),
        ).fetchall()

        return [
            {
                "path": row["path"],
                "chunk_id": row["chunk_id"],
                "content": row["content"],
                "rank": row["rank"],
            }
            for row in rows
        ]
    except Exception:
        return []


def search_for_prompt(query: str, limit: int = 3) -> str:
    """Search and format results as context for prompt injection.

    Returns formatted string:
        [RAG: filename]
        content

        [RAG: filename2]
        content2
    """
    results = search(query, limit=limit)
    if not results:
        return ""

    parts = []
    for r in results:
        filename = Path(r["path"]).name
        parts.append(f"[RAG: {filename}]\n{r['content']}")

    return "\n\n".join(parts)


def is_rag_query(query: str) -> bool:
    """Detect queries that reference personal documents."""
    if not query:
        return False
    return bool(_rag_re.search(query))


def get_index_stats() -> dict:
    """Return index statistics.

    Returns:
        {"total_docs": int, "total_chunks": int, "total_size": int, "last_indexed": str|None}
    """
    conn = get_db()
    ensure_tables(conn)
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS total_docs,
                      COALESCE(SUM(chunk_count), 0) AS total_chunks,
                      COALESCE(SUM(size_bytes), 0) AS total_size,
                      MAX(indexed_at) AS last_indexed
               FROM document_meta"""
        ).fetchone()
        return {
            "total_docs": row["total_docs"],
            "total_chunks": row["total_chunks"],
            "total_size": row["total_size"],
            "last_indexed": row["last_indexed"],
        }
    except Exception:
        return {"total_docs": 0, "total_chunks": 0, "total_size": 0, "last_indexed": None}


def clear_index() -> None:
    """Drop and recreate FTS5 table and metadata table."""
    conn = get_db()
    conn.execute("DROP TABLE IF EXISTS documents")
    conn.execute("DROP TABLE IF EXISTS document_meta")
    conn.commit()
    # Recreate empty tables
    ensure_tables()


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 rag.py index <directory>   — index a directory")
        print('  python3 rag.py search "query"      — search and print results')
        print("  python3 rag.py stats               — show index stats")
        print("  python3 rag.py clear               — clear index")
        sys.exit(1)

    command = sys.argv[1]

    if command == "index":
        if len(sys.argv) < 3:
            print("Error: specify a directory to index")
            sys.exit(1)
        target = sys.argv[2]
        print(f"Indexing {target} ...")
        t0 = time.monotonic()
        stats = index_directory(target)
        elapsed = time.monotonic() - t0
        print(
            f"Done in {elapsed:.1f}s — "
            f"indexed: {stats['indexed']}, "
            f"skipped: {stats['skipped']}, "
            f"errors: {stats['errors']}"
        )

    elif command == "search":
        if len(sys.argv) < 3:
            print("Error: specify a search query")
            sys.exit(1)
        q = " ".join(sys.argv[2:])
        results = search(q, limit=10)
        if not results:
            print("No results found.")
        else:
            for i, r in enumerate(results, 1):
                fname = Path(r["path"]).name
                preview = r["content"][:200].replace("\n", " ")
                print(f"\n--- Result {i} (rank: {r['rank']:.4f}) ---")
                print(f"File: {r['path']}")
                print(f"Chunk: {r['chunk_id']}")
                print(f"Preview: {preview}...")

    elif command == "stats":
        s = get_index_stats()
        print(f"Documents: {s['total_docs']}")
        print(f"Chunks:    {s['total_chunks']}")
        print(f"Size:      {_format_size(s['total_size'])}")
        print(f"Last indexed: {s['last_indexed'] or 'never'}")

    elif command == "clear":
        clear_index()
        print("Index cleared.")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
