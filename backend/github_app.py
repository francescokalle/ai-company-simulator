"""
GitHub App Integration - Official bot authentication via GitHub App.

Flow (per GitHub docs):
1. App ID + Private Key (PEM) -> signed JWT (RS256)
2. JWT -> list installations / get repo installation
3. JWT + Installation ID -> installation access token (1h expiry)
4. Installation token -> clone private repos, read contents, invite collaborators

Docs:
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app
"""
import time
import logging
import subprocess
from pathlib import Path
from typing import Optional

import jwt
import httpx

logger = logging.getLogger(__name__)

API_VERSION = "2022-11-28"


class GitHubApp:
    """Manages GitHub App authentication and operations."""

    def __init__(self, app_id: str, private_key: str, client_id: Optional[str] = None):
        self.app_id = app_id
        self.private_key = private_key
        self.client_id = client_id
        self._jwt_token: Optional[str] = None
        self._jwt_expiry: float = 0

    # ---------- Step 1: JWT ----------

    def _generate_jwt(self) -> str:
        """Generate a signed JWT for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now - 60,   # 60s in the past to tolerate clock drift
            "exp": now + 600,  # max 10 minutes
            "iss": self.app_id,
        }
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        self._jwt_token = token
        self._jwt_expiry = now + 600
        return token

    def _get_jwt(self) -> str:
        """Get a valid JWT, regenerating when close to expiry."""
        if not self._jwt_token or time.time() > self._jwt_expiry - 60:
            return self._generate_jwt()
        return self._jwt_token

    def _headers(self, token: str, as_installation: bool = False) -> dict:
        """Build GitHub API headers with the required API version."""
        return {
            "Authorization": f"Bearer {token}" if as_installation else f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        }

    # ---------- Step 3: Installation access token ----------

    async def get_installation_token(self, installation_id: int) -> str:
        """Exchange JWT for an installation access token (expires in 1h)."""
        jwt_token = self._get_jwt()
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                },
            )
            resp.raise_for_status()
            return resp.json()["token"]

    # ---------- Installations ----------

    async def get_installations(self) -> list[dict]:
        """List all installations of this GitHub App."""
        jwt_token = self._get_jwt()
        url = "https://api.github.com/app/installations"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_repo_installation(self, owner: str, repo: str) -> Optional[dict]:
        """
        Get the installation that can access a repo, via the official
        GET /repos/{owner}/{repo}/installation endpoint (requires JWT).
        Returns {"id": ..., ...} or None when the App is not installed there.
        """
        jwt_token = self._get_jwt()
        url = f"https://api.github.com/repos/{owner}/{repo}/installation"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                },
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return None

    async def find_installation_for_repo(self, owner: str, repo: str) -> Optional[dict]:
        """
        Find the installation with access to a specific repo.
        Tries the direct endpoint first, then falls back to scanning all installations.
        """
        inst = await self.get_repo_installation(owner, repo)
        if inst:
            return {"id": inst["id"], "account": inst.get("account", {}).get("login", "")}

        # Fallback: check every installation
        for item in await self.get_installations():
            inst_id = item.get("id")
            if inst_id is None:
                continue
            found = await self.get_repo_installation(owner, repo)
            if found:
                return {"id": found["id"], "account": found.get("account", {}).get("login", "")}
        return None

    # ---------- Repository operations ----------

    async def get_repo_token(self, owner: str, repo: str) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve the installation token for a repo.
        Returns (installation_token, error_message). One of the two is None.
        """
        inst = await self.find_installation_for_repo(owner, repo)
        if not inst:
            return None, (
                "La GitHub App non è installata su questa repository. "
                "Installala da https://github.com/settings/installations "
                "selezionando la repo, con permessi 'Contents: read' e 'Administration: write'."
            )
        token = await self.get_installation_token(int(inst["id"]))
        return token, None

    async def clone_repo(self, owner: str, repo: str, dest_path: Path) -> Path:
        """
        Clone a repository using an installation token (works for private repos).
        Raises RuntimeError with a readable message on failure.
        """
        token, err = await self.get_repo_token(owner, repo)
        if not token:
            raise RuntimeError(err)

        url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            # Never leak the token in the error message
            safe_err = result.stderr.replace(token, "***")
            raise RuntimeError(f"Git clone failed: {safe_err}")
        return dest_path

    # ---------- Collaborators ----------

    async def get_app_info(self) -> dict:
        """Get the App's own metadata (name, slug, owner) using the JWT."""
        jwt_token = self._get_jwt()
        url = "https://api.github.com/app"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_install_url(self, owner: str, repo: str) -> str:
        """
        Build the URL where the user installs the App on their repo.
        GitHub Apps are NOT users: they cannot be invited as collaborators.
        They must be installed, which requires one click by the user.
        """
        try:
            info = await self.get_app_info()
            slug = info.get("slug", "")
            if slug:
                return f"https://github.com/apps/{slug}/installations/new?repository={owner}/{repo}"
        except Exception as e:
            logger.warning(f"Could not resolve app slug: {e}")
        return f"https://github.com/settings/installations"

    async def check_installation(self, owner: str, repo: str) -> dict:
        """
        Verify whether the App is installed and can access the repo.
        Returns status, install URL, and permissions info.
        """
        try:
            inst = await self.get_repo_installation(owner, repo)
        except Exception as e:
            return {
                "installed": False,
                "error": f"Impossibile verificare l'installazione: {e}",
                "install_url": await self.get_install_url(owner, repo),
            }

        if not inst:
            return {
                "installed": False,
                "error": "La GitHub App non è installata su questa repository.",
                "install_url": await self.get_install_url(owner, repo),
            }

        # Verify the installation token actually grants repo access
        try:
            token = await self.get_installation_token(int(inst["id"]))
        except Exception as e:
            return {
                "installed": False,
                "error": f"Installazione trovata ma token non ottenibile: {e}",
                "install_url": await self.get_install_url(owner, repo),
            }

        # Check what permissions the installation has
        perms = inst.get("permissions", {})
        contents_perm = perms.get("contents", "none")
        admin_perm = perms.get("administration", "none")

        missing = []
        if contents_perm not in ("read", "write"):
            missing.append("Contents: Read")
        if admin_perm not in ("read", "write"):
            missing.append("Administration: Read and write")

        return {
            "installed": True,
            "installation_id": inst["id"],
            "account": inst.get("account", {}).get("login", ""),
            "permissions": {"contents": contents_perm, "administration": admin_perm},
            "missing_permissions": missing,
            "token_ok": bool(token),
        }

    async def invite_collaborator(
        self,
        installation_token: str,
        owner: str,
        repo: str,
        username: str,
        permission: str = "push",
    ) -> dict:
        """
        Add a user as repository collaborator.
        Requires the App to have "Administration: write" permission.
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/collaborators/{username}"
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                headers={
                    "Authorization": f"token {installation_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                    "Content-Type": "application/json",
                },
                json={"permission": permission},
            )
            if resp.status_code in (200, 201, 204):
                return {"success": True, "status": resp.status_code}
            return {
                "success": False,
                "status": resp.status_code,
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
            }

    async def create_repo(
        self,
        installation_token: str,
        name: str,
        description: str = "",
        private: bool = True,
    ) -> dict:
        """Create a repository as the App installation."""
        url = "https://api.github.com/user/repos"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"token {installation_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
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
