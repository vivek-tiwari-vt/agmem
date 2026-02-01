"""
Vector store for semantic search over agmem memory.

Uses sqlite-vec for local vector storage and sentence-transformers for embeddings.
Requires: pip install agmem[vector]
"""

import logging
import struct
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import MEMORY_TYPES

logger = logging.getLogger("agmem.vector_store")

# Embedding dimension for all-MiniLM-L6-v2
EMBEDDING_DIM = 384


def _serialize_f32(vector: List[float]) -> bytes:
    """Serialize float list to bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


class VectorStore:
    """Semantic search over memory using vector embeddings."""

    def __init__(self, mem_dir: Path):
        self.mem_dir = Path(mem_dir)
        self.db_path = self.mem_dir / "vectors.db"
        self._model = None
        self._conn = None

    def _get_connection(self):
        """Get SQLite connection with sqlite-vec loaded."""
        if self._conn is not None:
            return self._conn

        try:
            import sqlite3
            import sqlite_vec

            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            return self._conn
        except ImportError as e:
            raise ImportError(
                "Vector search requires sqlite-vec. Install with: pip install agmem[vector]"
            ) from e
        except AttributeError as e:
            raise ImportError(
                "SQLite extension loading not supported. "
                "On macOS, try: brew install python (for Homebrew SQLite)"
            ) from e

    def _get_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            return self._model
        except ImportError as e:
            raise ImportError(
                "Vector search requires sentence-transformers. "
                "Install with: pip install agmem[vector]"
            ) from e

    def _ensure_tables(self):
        """Create vector and metadata tables if they don't exist."""
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_meta (
                rowid INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                content TEXT NOT NULL,
                blob_hash TEXT,
                commit_hash TEXT,
                author TEXT,
                indexed_at TEXT
            )
        """
        )
        # Try to add new columns to existing tables (for upgrades)
        for col in ["commit_hash TEXT", "author TEXT", "indexed_at TEXT"]:
            try:
                conn.execute(f"ALTER TABLE memory_meta ADD COLUMN {col}")
            except Exception:
                pass  # Column already exists
        try:
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_memory
                USING vec0(embedding float[{EMBEDDING_DIM}])
            """
            )
        except Exception as e:
            # vec0 might already exist with different schema
            logger.debug("vec_memory creation: %s", e)
        conn.commit()

    def _embed(self, text: str) -> List[float]:
        """Generate embedding for text."""
        model = self._get_model()
        emb = model.encode(text, convert_to_numpy=True)
        return emb.astype("float32").tolist()

    def index_content(
        self,
        path: str,
        content: str,
        blob_hash: Optional[str] = None,
        commit_hash: Optional[str] = None,
        author: Optional[str] = None,
    ) -> None:
        """
        Index a memory file for semantic search.

        Args:
            path: File path relative to current/
            content: File content to index
            blob_hash: Optional blob hash from object store
            commit_hash: Optional commit hash for provenance tracking
            author: Optional author string for provenance tracking
        """
        from datetime import datetime

        self._ensure_tables()
        conn = self._get_connection()

        embedding = self._embed(content)
        emb_bytes = _serialize_f32(embedding)
        indexed_at = datetime.utcnow().isoformat() + "Z"

        with conn:
            conn.execute(
                """INSERT INTO memory_meta 
                   (path, content, blob_hash, commit_hash, author, indexed_at) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (path, content[:10000], blob_hash, commit_hash, author, indexed_at),
            )
            rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO vec_memory (rowid, embedding) VALUES (?, ?)",
                (rowid, emb_bytes),
            )
        conn.commit()

    def index_directory(self, current_dir: Path) -> int:
        """Index all memory files in current/ directory. Returns count indexed."""
        self._ensure_tables()
        count = 0

        for subdir in MEMORY_TYPES:
            dir_path = current_dir / subdir
            if not dir_path.exists():
                continue
            for f in dir_path.rglob("*"):
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                        rel_path = str(f.relative_to(current_dir))
                        self.index_content(rel_path, content)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to index %s: %s", f, e)

        return count

    def search(
        self, query: str, limit: int = 10, min_score: Optional[float] = None
    ) -> List[Tuple[str, str, float]]:
        """
        Semantic search. Returns list of (path, content_snippet, distance).
        Lower distance = more similar.
        """
        self._ensure_tables()
        conn = self._get_connection()

        query_embedding = self._embed(query)
        emb_bytes = _serialize_f32(query_embedding)

        rows = conn.execute(
            """
            SELECT m.path, m.content, v.distance
            FROM vec_memory v
            JOIN memory_meta m ON v.rowid = m.rowid
            WHERE v.embedding MATCH ?
            ORDER BY v.distance
            LIMIT ?
            """,
            (emb_bytes, limit),
        ).fetchall()

        results = []
        for path, content, distance in rows:
            if min_score is not None and distance > min_score:
                continue
            snippet = content[:500] + ("..." if len(content) > 500 else "")
            results.append((path, snippet, float(distance)))

        return results

    def search_with_provenance(
        self, query: str, limit: int = 10, min_score: Optional[float] = None
    ) -> List[dict]:
        """
        Semantic search with provenance metadata.

        Returns list of dicts with: path, content, distance, commit_hash, author, indexed_at
        """
        self._ensure_tables()
        conn = self._get_connection()

        query_embedding = self._embed(query)
        emb_bytes = _serialize_f32(query_embedding)

        rows = conn.execute(
            """
            SELECT m.path, m.content, v.distance, m.commit_hash, m.author, m.indexed_at, m.blob_hash
            FROM vec_memory v
            JOIN memory_meta m ON v.rowid = m.rowid
            WHERE v.embedding MATCH ?
            ORDER BY v.distance
            LIMIT ?
            """,
            (emb_bytes, limit),
        ).fetchall()

        results = []
        for path, content, distance, commit_hash, author, indexed_at, blob_hash in rows:
            if min_score is not None and distance > min_score:
                continue
            snippet = content[:500] + ("..." if len(content) > 500 else "")
            results.append(
                {
                    "path": path,
                    "content": snippet,
                    "distance": float(distance),
                    "similarity": 1.0 - float(distance),  # Convert to similarity score
                    "commit_hash": commit_hash,
                    "author": author,
                    "indexed_at": indexed_at,
                    "blob_hash": blob_hash,
                }
            )

        return results

    def get_all_entries(self) -> List[dict]:
        """
        Get all indexed entries with their metadata.

        Used for fsck operations to check for dangling vectors.
        """
        self._ensure_tables()
        conn = self._get_connection()

        rows = conn.execute(
            """
            SELECT rowid, path, blob_hash, commit_hash, author, indexed_at
            FROM memory_meta
            """
        ).fetchall()

        return [
            {
                "rowid": rowid,
                "path": path,
                "blob_hash": blob_hash,
                "commit_hash": commit_hash,
                "author": author,
                "indexed_at": indexed_at,
            }
            for rowid, path, blob_hash, commit_hash, author, indexed_at in rows
        ]

    def delete_entry(self, rowid: int) -> bool:
        """
        Delete an entry by rowid.

        Used by fsck to remove dangling vectors.
        """
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM memory_meta WHERE rowid = ?", (rowid,))
                conn.execute("DELETE FROM vec_memory WHERE rowid = ?", (rowid,))
            conn.commit()
            return True
        except Exception as e:
            logger.warning("Failed to delete entry %s: %s", rowid, e)
            return False

    def rebuild_index(self, current_dir: Path) -> int:
        """Clear and rebuild the vector index from current/."""
        conn = self._get_connection()
        with conn:
            try:
                conn.execute("DROP TABLE IF EXISTS vec_memory")
            except Exception:
                pass
            conn.execute("DELETE FROM memory_meta")
        conn.commit()
        self._ensure_tables()
        return self.index_directory(current_dir)

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
