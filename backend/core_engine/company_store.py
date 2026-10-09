"""
Company Store - Multi-company persistence with SQLite.

Allows saving, listing, switching, pausing and resuming companies.
State (offices, agents metadata) survives server restarts.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "companies.db"


class CompanyStore:
    """Persists companies so they can be managed and restored."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    source TEXT,
                    status TEXT DEFAULT 'paused',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    state_json TEXT
                )
            """)
            await db.commit()
        self._initialized = True
        logger.info("Company store initialized")

    async def save(self, company_id: str, user_id: int, name: str,
                   source: str = "", status: str = "paused", state: dict | None = None) -> bool:
        """Insert or update a company."""
        if not self._initialized:
            await self.initialize()
        state_json = json.dumps(state or {})
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO companies (id, user_id, name, source, status, state_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    source = excluded.source,
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (company_id, user_id, name, source, status, state_json))
            await db.commit()
        return True

    async def list_companies(self, user_id: int) -> list[dict]:
        """List all companies for a user (without the heavy state blob)."""
        if not self._initialized:
            await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, name, source, status, created_at, updated_at
                FROM companies WHERE user_id = ? ORDER BY updated_at DESC
            """, (user_id,))
            rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "name": r[1], "source": r[2], "status": r[3],
                "created_at": r[4], "updated_at": r[5],
            }
            for r in rows
        ]

    async def get(self, company_id: str, user_id: int) -> Optional[dict]:
        """Get one company with its state, scoped to the owning user."""
        if not self._initialized:
            await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, user_id, name, source, status, created_at, updated_at, state_json
                FROM companies WHERE id = ? AND user_id = ?
            """, (company_id, user_id))
            row = await cursor.fetchone()
        if not row:
            return None
        try:
            state = json.loads(row[7]) if row[7] else {}
        except json.JSONDecodeError:
            state = {}
        return {
            "id": row[0], "user_id": row[1], "name": row[2], "source": row[3],
            "status": row[4], "created_at": row[5], "updated_at": row[6], "state": state,
        }

    async def set_status(self, company_id: str, user_id: int, status: str) -> bool:
        """Update a company's status (running/paused/stopped)."""
        if not self._initialized:
            await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE companies SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            """, (status, company_id, user_id))
            await db.commit()
            return cursor.rowcount > 0

    async def delete(self, company_id: str, user_id: int) -> bool:
        """Delete a company."""
        if not self._initialized:
            await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM companies WHERE id = ? AND user_id = ?",
                (company_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_active(self, user_id: int) -> Optional[dict]:
        """Get the currently running company for a user, if any."""
        if not self._initialized:
            await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT id, name, source, status, created_at, updated_at, state_json
                FROM companies WHERE user_id = ? AND status = 'running'
                ORDER BY updated_at DESC LIMIT 1
            """, (user_id,))
            row = await cursor.fetchone()
        if not row:
            return None
        try:
            state = json.loads(row[6]) if row[6] else {}
        except json.JSONDecodeError:
            state = {}
        return {
            "id": row[0], "name": row[1], "source": row[2], "status": row[3],
            "created_at": row[4], "updated_at": row[5], "state": state,
        }
