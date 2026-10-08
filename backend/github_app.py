"""
GitHub App Integration - Official bot authentication via GitHub App.
Handles JWT generation, installation tokens, and Git operations.
"""
import time
import logging
from pathlib import Path
from typing import Optional

import jwt
import httpx

logger = logging.getLogger(__name__)


class GitHubApp:
    """Manages GitHub App authentication and operations."""

    def __init__(self, app_id: str, private_key: str, client_id: str | None = None):
        self.app_id = app_id
        self.private_key = private_key
        self.client_id = client_id
        self._jwt_token: str | None = None
        self._jwt_expiry: float = 0

    def _generate_jwt(self) -> str:
        """Generate a JWT token for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # 60 seconds in the past to allow for clock drift
            "exp": now + 600,  # 10 minutes expiry
            "iss": self.app_id,
        }
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        self._jwt_token = token
        self._jwt_expiry = now + 600
        return token

    def _get_jwt(self) -> str:
        """Get a valid JWT token, regenerating if expired."""
        if not self._jwt_token or time.time() > self._jwt_expiry - 60:
            return self._generate_jwt()
        return self._jwt_token

    async def get_installation_token(self, installation_id: int) -> str:
        """Get an installation access token for a specific installation."""
        jwt_token = self._get_jwt()
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            resp.raise_for_status()
            return resp.json()["token"]

    async def get_installations(self) -> list[dict]:
        """Get all installations of this GitHub App."""
        jwt_token = self._get_jwt()
        url = "https://api.github.com/app/installations"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def invite_collaborator(
        self,
        installation_token: str,
        owner: str,
        repo: str,
        username: str,
        permission: str = "push",
    ) -> dict:
        """Invite a collaborator to a repository."""
        url = f"https://api.github.com/repos/{owner}/{repo}/collaborators/{username}"
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                headers={
                    "Authorization": f"token {installation_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
                json={"permission": permission},
            )
            if resp.status_code in (200, 201, 204):
                return {"success": True, "status": resp.status_code}
            return {"success": False, "status": resp.status_code, "error": resp.text}

    async def clone_repo(
        self,
        installation_token: str,
        owner: str,
        repo: str,
        dest_path: Path,
    ) -> Path:
        """Clone a repository using the installation token."""
        import subprocess

        url = f"https://x-access-token:{installation_token}@github.com/{owner}/{repo}.git"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise Exception(f"Git clone failed: {result.stderr}")
        return dest_path

    async def create_repo(
        self,
        installation_token: str,
        name: str,
        description: str = "",
        private: bool = True,
    ) -> dict:
        """Create a new repository."""
        url = "https://api.github.com/user/repos"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"token {installation_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
                json={
                    "name": name,
                    "description": description,
                    "private": private,
                },
            )
            resp.raise_for_status()
            return resp.json()
