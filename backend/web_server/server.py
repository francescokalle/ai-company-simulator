"""
Web Server - FastAPI backend with WebSocket support for real-time simulation.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

from core_engine.engine import CompanyEngine
from github_app import GitHubApp
from auth import AuthManager

logger = logging.getLogger(__name__)


# Auth manager (module-level so lifespan can access it)
auth_manager = AuthManager()


def create_app(engine: CompanyEngine) -> FastAPI:
    """Create and configure the FastAPI application."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        await auth_manager.initialize()
        yield
        # Shutdown
        pass

    app = FastAPI(
        title="AI Virtual Company Simulator",
        description="Multi-agent virtual company simulation platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # WebSocket connection manager
    ws_manager = WebSocketManager(engine)

    def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
        """Dependency: validate the bearer token synchronously (SQLite is fast)."""
        if not credentials or not credentials.credentials:
            raise HTTPException(status_code=401, detail="Missing token")
        # SQLite validation is a fast local read; run it directly
        import sqlite3
        try:
            conn = sqlite3.connect(str(auth_manager.db_path.resolve()))
            cursor = conn.execute(
                "SELECT s.token FROM sessions s WHERE s.token = ? AND s.expires_at > datetime('now')",
                (credentials.credentials,),
            )
            row = cursor.fetchone()
            conn.close()
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise HTTPException(status_code=500, detail="Auth backend error")
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return credentials.credentials

    # Static files (frontend build)
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    # API Routes
    @app.get("/")
    async def root():
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "AI Virtual Company Simulator API", "status": "running"}

    @app.post("/api/auth/login")
    async def login(username: str = Form(...), password: str = Form(...)):
        """Authenticate and receive a session token."""
        result = await auth_manager.login(username, password)
        if not result["success"]:
            raise HTTPException(status_code=401, detail=result["error"])
        return {"success": True, "token": result["token"], "username": username}

    @app.post("/api/auth/logout")
    async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Logout and invalidate the session token."""
        await auth_manager.logout(credentials.credentials)
        return {"success": True, "message": "Logged out successfully"}

    @app.get("/api/auth/me")
    async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Get current authenticated user info."""
        user = await auth_manager.validate_token(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": user["username"], "user_id": user["user_id"]}

    @app.post("/api/onboard")
    async def onboard_project(
        api_key: str = Form(...),
        project_name: str = Form(...),
        project_file: UploadFile = File(None),
        github_url: str = Form(None),
        github_app_id: str = Form(None),
        github_app_private_key: str = Form(None),
        github_installation_id: str = Form(None),
        github_collaborator: str = Form(None),
        optional_offices: str = Form(""),
        token: str = Depends(verify_token),
    ):
        """Onboard a new project and create the virtual company."""
        try:
            # Determine project source
            if github_url:
                project_source = github_url
            elif project_file:
                # Save uploaded file
                upload_dir = Path(__file__).parent.parent.parent / "data" / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                file_path = upload_dir / project_file.filename

                content = await project_file.read()
                file_path.write_bytes(content)
                project_source = str(file_path)
            else:
                raise HTTPException(status_code=400, detail="Either project_file or github_url must be provided")

            # Parse optional offices
            offices = [o.strip() for o in optional_offices.split(",") if o.strip()]

            # Onboard
            result = await engine.onboard_project(
                api_key=api_key,
                project_source=project_source,
                project_name=project_name,
                optional_offices=offices,
            )

            # Broadcast to all WebSocket clients
            await ws_manager.broadcast({
                "type": "company_created",
                "data": result,
            })

            return result
        except Exception as e:
            logger.error(f"Onboarding failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/github/invite")
    async def github_invite(request: dict, token: str = Depends(verify_token)):
        """Invite the bot collaborator via GitHub App. Installation ID is auto-discovered."""
        try:
            app_id = request.get("app_id")
            owner = request.get("owner")
            repo = request.get("repo")
            collaborator = request.get("collaborator", "the-agent-company")

            if not all([app_id, owner, repo]):
                raise HTTPException(status_code=400, detail="Missing required fields: app_id, owner, repo")

            # Read private key from local file (never from request)
            key_path = Path(__file__).resolve().parent.parent.parent / ".secrets" / "github-app-private-key.pem"
            if not key_path.exists():
                return {"success": False, "error": "GitHub App private key not configured on server"}

            private_key = key_path.read_text()

            gh_app = GitHubApp(app_id=str(app_id), private_key=private_key)

            # Auto-discover the installation that has access to this repo
            installation = await gh_app.find_installation_for_repo(str(owner), str(repo))
            if not installation:
                return {
                    "success": False,
                    "error": "No GitHub App installation found with access to this repository. "
                             "Install the App on the repo first: https://github.com/settings/installations",
                }

            inst_id = int(installation["id"])
            inst_token = await gh_app.get_installation_token(inst_id)
            result = await gh_app.invite_collaborator(inst_token, str(owner), str(repo), str(collaborator))

            if result["success"]:
                return {"success": True, "message": f"Invitation sent to {collaborator}", "installation_id": inst_id}
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"GitHub invite failed: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/settings")
    async def get_settings(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Get saved settings for the current user."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        settings = await auth_manager.get_settings(user["user_id"])
        # Never return the raw API key
        settings["opencode_api_key"] = "***" if settings["opencode_api_key"] else ""
        return {"success": True, "settings": settings}

    @app.post("/api/settings")
    async def save_settings(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        opencode_api_key: str = Form(None),
        github_repo_url: str = Form(None),
        github_app_id: str = Form(None),
        optional_offices: str = Form(None),
        custom_offices: str = Form(None),
    ):
        """Save settings for the current user."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = await auth_manager.save_settings(
            user_id=user["user_id"],
            opencode_api_key=opencode_api_key,
            github_repo_url=github_repo_url,
            github_app_id=github_app_id,
            optional_offices=[o.strip() for o in optional_offices.split(",") if o.strip()] if optional_offices is not None else None,
            custom_offices=[o.strip() for o in custom_offices.split(",") if o.strip()] if custom_offices is not None else None,
        )
        return result

    @app.post("/api/message")
    async def send_message(
        message: str = Form(...),
        token: str = Depends(verify_token),
    ):
        """Send a message to the CEO agent."""
        try:
            response = await engine.handle_user_message(message)
            return {"response": response}
        except Exception as e:
            logger.error(f"Message handling failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/state")
    async def get_state(token: str = Depends(verify_token)):
        """Get current company state."""
        return await engine.get_company_state()

    @app.get("/api/agents/{agent_id}")
    async def get_agent(agent_id: str, token: str = Depends(verify_token)):
        """Get detailed information about a specific agent."""
        return await engine.get_agent_details(agent_id)

    @app.get("/api/offices")
    async def get_offices(token: str = Depends(verify_token)):
        """Get all offices."""
        return {"offices": engine.offices}

    @app.get("/api/memory/search")
    async def search_memory(q: str, n: int = 5, token: str = Depends(verify_token)):
        """Search project memory."""
        if engine.vector_store:
            results = await engine.vector_store.search(q, n_results=n)
            return {"results": results}
        return {"results": []}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = None):
        """WebSocket endpoint for real-time simulation events."""
        # Accept token via query param (WebSocket can't set headers easily)
        if not token:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        user = await auth_manager.validate_token(token)
        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        await ws_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive and handle client messages
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg.get("type") == "get_state":
                    state = await engine.get_company_state()
                    await websocket.send_json({"type": "state", "data": state})
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            ws_manager.disconnect(websocket)

    return app


class WebSocketManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self, engine: CompanyEngine):
        self.engine = engine
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

        # Send initial state
        state = await self.engine.get_company_state()
        await websocket.send_json({"type": "state", "data": state})

        # Subscribe to engine events (uses broadcast directly, no per-connection handler)
        # NOTE: subscription is done once per engine, not per connection, to avoid leaks
        self._ensure_subscribed()

    def _ensure_subscribed(self):
        """Subscribe the event bus to the shared broadcast (idempotent)."""
        if getattr(self, "_subscribed", False):
            return
        if not self.engine.event_bus:
            return

        async def _broadcast_handler(event: str, data: dict):
            await self.broadcast({"type": event, "data": data})

        for event_type in ("agent_walking", "agent_arrived", "intent_to_communicate",
                           "agent_fired", "request_new_agent"):
            self.engine.event_bus.subscribe(event_type, _broadcast_handler)

        self._subscribed = True

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    def _create_handler(self, event_type: str):
        """Create an event handler for a specific event type."""
        async def handler(event: str, data: dict):
            await self.broadcast({"type": event_type, "data": data})
        return handler

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
