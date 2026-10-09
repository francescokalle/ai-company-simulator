"""
Authentication System - User login with secure password hashing.
"""
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "auth.db"


class AuthManager:
    """Manages user authentication with SQLite backend."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self):
        """Initialize the auth database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    opencode_api_key TEXT,
                    github_repo_url TEXT,
                    github_app_id TEXT,
                    optional_offices TEXT,
                    custom_offices TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            await db.commit()
        self._initialized = True
        logger.info("Auth database initialized")

    def _hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt using PBKDF2."""
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        ).hex()

    async def register(self, username: str, password: str) -> dict:
        """Register a new user."""
        if not self._initialized:
            await self.initialize()

        salt = secrets.token_hex(32)
        password_hash = self._hash_password(password, salt)

        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, password_hash, salt),
                )
                await db.commit()
                return {"success": True, "user_id": cursor.lastrowid}
        except aiosqlite.IntegrityError:
            return {"success": False, "error": "Username already exists"}

    async def login(self, username: str, password: str) -> dict:
        """Authenticate a user and return a session token."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, password_hash, salt FROM users WHERE username = ?",
                (username,),
            )
            row = await cursor.fetchone()

            if not row:
                return {"success": False, "error": "Invalid username or password"}

            user_id, stored_hash, salt = row
            password_hash = self._hash_password(password, salt)

            if password_hash != stored_hash:
                return {"success": False, "error": "Invalid username or password"}

            # Update last login
            await db.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,),
            )

            # Create session
            token = secrets.token_urlsafe(32)
            await db.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, datetime('now', '+7 days'))",
                (token, user_id),
            )
            await db.commit()

            return {"success": True, "token": token, "user_id": user_id}

    async def validate_token(self, token: str) -> Optional[dict]:
        """Validate a session token."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT s.token, s.user_id, u.username 
                   FROM sessions s 
                   JOIN users u ON s.user_id = u.id 
                   WHERE s.token = ? AND s.expires_at > datetime('now')""",
                (token,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return {"token": row[0], "user_id": row[1], "username": row[2]}

    async def logout(self, token: str):
        """Invalidate a session token."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            await db.commit()

    async def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
            await db.commit()

    async def get_settings(self, user_id: int) -> dict:
        """Get saved settings for a user."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT opencode_api_key, github_repo_url, github_app_id, optional_offices, custom_offices "
                "FROM user_settings WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return {
                "opencode_api_key": "",
                "github_repo_url": "",
                "github_app_id": "",
                "optional_offices": [],
                "custom_offices": [],
            }

        return {
            "opencode_api_key": row[0] or "",
            "github_repo_url": row[1] or "",
            "github_app_id": row[2] or "",
            "optional_offices": [o for o in (row[3] or "").split(",") if o],
            "custom_offices": [o for o in (row[4] or "").split(",") if o],
        }

    async def save_settings(
        self,
        user_id: int,
        opencode_api_key: str | None = None,
        github_repo_url: str | None = None,
        github_app_id: str | None = None,
        optional_offices: list[str] | None = None,
        custom_offices: list[str] | None = None,
    ) -> dict:
        """Save (upsert) settings for a user. Only overwrites fields that are provided."""
        if not self._initialized:
            await self.initialize()

        current = await self.get_settings(user_id)

        new_values = {
            "opencode_api_key": opencode_api_key if opencode_api_key is not None else current["opencode_api_key"],
            "github_repo_url": github_repo_url if github_repo_url is not None else current["github_repo_url"],
            "github_app_id": github_app_id if github_app_id is not None else current["github_app_id"],
            "optional_offices": optional_offices if optional_offices is not None else current["optional_offices"],
            "custom_offices": custom_offices if custom_offices is not None else current["custom_offices"],
        }

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO user_settings (user_id, opencode_api_key, github_repo_url, github_app_id, optional_offices, custom_offices, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(user_id) DO UPDATE SET
                     opencode_api_key = excluded.opencode_api_key,
                     github_repo_url = excluded.github_repo_url,
                     github_app_id = excluded.github_app_id,
                     optional_offices = excluded.optional_offices,
                     custom_offices = excluded.custom_offices,
                     updated_at = CURRENT_TIMESTAMP""",
                (
                    user_id,
                    new_values["opencode_api_key"],
                    new_values["github_repo_url"],
                    new_values["github_app_id"],
                    ",".join(new_values["optional_offices"]),
                    ",".join(new_values["custom_offices"]),
                ),
            )
            await db.commit()

        return {"success": True, "settings": new_values}
