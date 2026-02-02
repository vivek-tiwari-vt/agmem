"""
Progressive Disclosure Search - SQLite FTS5 based multi-layer search.

Implements 3-tier search to minimize token usage while maximizing relevance:
- Layer 1: Lightweight Index (metadata + first line)
- Layer 2: Timeline Context (file summaries by date)
- Layer 3: Full Details (complete file content)
"""

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class IndexEntry:
    """A single entry in the search index."""

    file_hash: str
    path: str
    filename: str
    memory_type: str
    first_line: str
    modified_time: str
    size_bytes: int
    commit_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SearchResult:
    """A search result with relevance info."""

    path: str
    filename: str
    memory_type: str
    first_line: str
    snippet: str
    score: float
    modified_time: str
    size_bytes: int


@dataclass
class TimelineEntry:
    """A timeline entry grouping files by date."""

    date: str
    file_count: int
    files: List[Dict[str, str]]
    summary: Optional[str] = None


class SearchIndex:
    """SQLite FTS5 based search index for memory files."""

    SCHEMA = """
    -- Main index table
    CREATE TABLE IF NOT EXISTS file_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_hash TEXT UNIQUE NOT NULL,
        path TEXT NOT NULL,
        filename TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        first_line TEXT,
        content_preview TEXT,
        modified_time TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        commit_hash TEXT,
        metadata_json TEXT,
        indexed_at TEXT NOT NULL
    );

    -- FTS5 virtual table for full-text search (standalone)
    CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
        file_hash,
        path,
        filename,
        first_line,
        content_preview
    );

    -- Indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_memory_type ON file_index(memory_type);
    CREATE INDEX IF NOT EXISTS idx_modified_time ON file_index(modified_time);
    CREATE INDEX IF NOT EXISTS idx_path ON file_index(path);
    CREATE INDEX IF NOT EXISTS idx_file_hash ON file_index(file_hash);

    -- Timeline view helper table
    CREATE TABLE IF NOT EXISTS timeline_cache (
        date TEXT PRIMARY KEY,
        file_count INTEGER,
        files_json TEXT,
        updated_at TEXT
    );
    """

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.db_path = self.mem_dir / "search_index.db"
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection."""
        if self._conn is None:
            self.mem_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # Enable FTS5
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._conn
        cursor = conn.cursor()
        for statement in self.SCHEMA.split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    cursor.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # Table may already exist
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Indexing ---

    def index_file(self, path: Path, content: str, commit_hash: Optional[str] = None) -> str:
        """Index a single file. Returns the file hash."""
        conn = self._get_connection()

        # Calculate file hash
        file_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Extract metadata
        filename = path.name
        memory_type = self._extract_memory_type(path)
        first_line = self._extract_first_line(content)
        content_preview = content[:500]  # First 500 chars for FTS
        stat = path.stat() if path.exists() else None
        modified_time = (
            datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            if stat
            else datetime.now(timezone.utc).isoformat()
        )
        size_bytes = stat.st_size if stat else len(content.encode())

        # Parse YAML frontmatter for metadata
        metadata = self._extract_frontmatter(content)

        # Insert or replace in main table
        cursor = conn.cursor()

        # Delete existing entry if present (for proper FTS sync)
        cursor.execute("DELETE FROM file_fts WHERE file_hash = ?", (file_hash,))
        cursor.execute("DELETE FROM file_index WHERE file_hash = ?", (file_hash,))

        cursor.execute(
            """
            INSERT INTO file_index 
            (file_hash, path, filename, memory_type, first_line, content_preview, modified_time, size_bytes, commit_hash, metadata_json, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                file_hash,
                str(path),
                filename,
                memory_type,
                first_line,
                content_preview,
                modified_time,
                size_bytes,
                commit_hash,
                json.dumps(metadata) if metadata else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        # Insert into FTS index
        cursor.execute(
            """
            INSERT INTO file_fts (file_hash, path, filename, first_line, content_preview)
            VALUES (?, ?, ?, ?, ?)
        """,
            (file_hash, str(path), filename, first_line, content_preview),
        )

        conn.commit()
        return file_hash

    def index_directory(self, current_dir: Path) -> int:
        """Recursively index all files in current/ directory. Returns count of indexed files."""
        count = 0
        for memory_type in ["episodic", "semantic", "procedural"]:
            type_dir = current_dir / memory_type
            if not type_dir.exists():
                continue

            for filepath in type_dir.rglob("*"):
                if filepath.is_file():
                    try:
                        content = filepath.read_text(encoding="utf-8", errors="replace")
                        self.index_file(filepath, content)
                        count += 1
                    except Exception:
                        pass

        self._update_timeline_cache()
        return count

    def _extract_memory_type(self, path: Path) -> str:
        """Extract memory type from path."""
        parts = path.parts
        for memory_type in ["episodic", "semantic", "procedural"]:
            if memory_type in parts:
                return memory_type
        return "unknown"

    def _extract_first_line(self, content: str) -> str:
        """Extract meaningful first line from content."""
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            # Skip frontmatter delimiters and empty lines
            if line and line != "---" and not line.startswith("#"):
                return line[:200]
            # Use first heading if present
            if line.startswith("#"):
                return line.lstrip("#").strip()[:200]
        return lines[0][:200] if lines else ""

    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract YAML frontmatter if present."""
        if not content.startswith("---"):
            return None

        try:
            end = content.find("---", 3)
            if end == -1:
                return None
            frontmatter = content[3:end].strip()

            # Simple YAML parsing (key: value only)
            metadata = {}
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip().strip('"').strip("'")
            return metadata
        except Exception:
            return None

    def _update_timeline_cache(self) -> None:
        """Update the timeline cache table."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Group files by date
        cursor.execute(
            """
            SELECT DATE(modified_time) as date, COUNT(*) as count,
                   GROUP_CONCAT(path || '|' || filename || '|' || memory_type, ';;') as files
            FROM file_index
            GROUP BY DATE(modified_time)
            ORDER BY date DESC
        """
        )

        for row in cursor.fetchall():
            files_list = []
            if row["files"]:
                for file_str in row["files"].split(";;"):
                    parts = file_str.split("|")
                    if len(parts) >= 3:
                        files_list.append(
                            {
                                "path": parts[0],
                                "filename": parts[1],
                                "memory_type": parts[2],
                            }
                        )

            cursor.execute(
                """
                INSERT OR REPLACE INTO timeline_cache (date, file_count, files_json, updated_at)
                VALUES (?, ?, ?, ?)
            """,
                (
                    row["date"],
                    row["count"],
                    json.dumps(files_list),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        conn.commit()

    # --- Layer 1: Lightweight Index Search ---

    def search_index(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[SearchResult]:
        """Layer 1: Search the lightweight index. Returns metadata + first line only."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build FTS5 query
        fts_query = self._build_fts_query(query)

        sql = """
            SELECT f.path, f.filename, f.memory_type, f.first_line, f.modified_time, f.size_bytes,
                   bm25(file_fts) as score,
                   snippet(file_fts, 4, '<b>', '</b>', '...', 32) as snippet
            FROM file_fts
            JOIN file_index f ON file_fts.file_hash = f.file_hash
            WHERE file_fts MATCH ?
        """
        params: List[Any] = [fts_query]

        if memory_type:
            sql += " AND f.memory_type = ?"
            params.append(memory_type)

        sql += " ORDER BY score LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)

        results = []
        for row in cursor.fetchall():
            results.append(
                SearchResult(
                    path=row["path"],
                    filename=row["filename"],
                    memory_type=row["memory_type"],
                    first_line=row["first_line"],
                    snippet=row["snippet"] or "",
                    score=abs(row["score"]),
                    modified_time=row["modified_time"],
                    size_bytes=row["size_bytes"],
                )
            )

        return results

    def _build_fts_query(self, query: str) -> str:
        """Build FTS5 query from user query."""
        # Simple tokenization - split on spaces, add wildcard for prefix matching
        tokens = query.strip().split()
        if not tokens:
            return "*"

        # For single token, use prefix match
        if len(tokens) == 1:
            return f'"{tokens[0]}"*'

        # For multiple tokens, use AND with prefix match on last token
        parts = [f'"{t}"' for t in tokens[:-1]]
        parts.append(f'"{tokens[-1]}"*')
        return " AND ".join(parts)

    # --- Layer 2: Timeline Context ---

    def get_timeline(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
    ) -> List[TimelineEntry]:
        """Layer 2: Get timeline of files grouped by date."""
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = "SELECT date, file_count, files_json FROM timeline_cache"
        conditions = []
        params: List[Any] = []

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)

        results = []
        for row in cursor.fetchall():
            files = json.loads(row["files_json"]) if row["files_json"] else []
            results.append(
                TimelineEntry(
                    date=row["date"],
                    file_count=row["file_count"],
                    files=files,
                )
            )

        return results

    def get_context_around(
        self,
        path: str,
        window_hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """Get files modified around the same time as a given file."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get the file's modification time
        cursor.execute("SELECT modified_time FROM file_index WHERE path = ?", (path,))
        row = cursor.fetchone()
        if not row:
            return []

        base_time = row["modified_time"]

        # Find files within the time window
        cursor.execute(
            """
            SELECT path, filename, memory_type, first_line, modified_time
            FROM file_index
            WHERE ABS(JULIANDAY(modified_time) - JULIANDAY(?)) * 24 <= ?
            AND path != ?
            ORDER BY ABS(JULIANDAY(modified_time) - JULIANDAY(?))
            LIMIT 20
        """,
            (base_time, window_hours, path, base_time),
        )

        return [dict(row) for row in cursor.fetchall()]

    # --- Layer 3: Full Details ---

    def get_full_details(self, paths: List[str]) -> List[Dict[str, Any]]:
        """Layer 3: Get full file details for specific paths."""
        results = []
        for path in paths:
            filepath = Path(path)
            if not filepath.exists():
                continue

            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                results.append(
                    {
                        "path": str(path),
                        "filename": filepath.name,
                        "content": content,
                        "size_bytes": len(content.encode()),
                    }
                )
            except Exception:
                pass

        return results

    # --- Statistics ---

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM file_index")
        total = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT memory_type, COUNT(*) as count 
            FROM file_index 
            GROUP BY memory_type
        """
        )
        by_type = {row["memory_type"]: row["count"] for row in cursor.fetchall()}

        cursor.execute("SELECT SUM(size_bytes) as total_size FROM file_index")
        total_size = cursor.fetchone()["total_size"] or 0

        return {
            "total_files": total,
            "by_type": by_type,
            "total_size_bytes": total_size,
            "db_path": str(self.db_path),
        }


# --- Token Cost Estimation ---


def estimate_token_cost(text: str) -> int:
    """Estimate token count for text (rough approximation)."""
    # Rough estimate: ~4 characters per token
    return len(text) // 4


def layer1_cost(results: List[SearchResult]) -> int:
    """Estimate token cost for Layer 1 results."""
    total = 0
    for r in results:
        total += estimate_token_cost(r.path + r.first_line + r.snippet)
    return total


def layer2_cost(timeline: List[TimelineEntry]) -> int:
    """Estimate token cost for Layer 2 results."""
    total = 0
    for t in timeline:
        total += estimate_token_cost(str(t.files))
    return total


def layer3_cost(details: List[Dict[str, Any]]) -> int:
    """Estimate token cost for Layer 3 results."""
    total = 0
    for d in details:
        total += estimate_token_cost(d.get("content", ""))
    return total
