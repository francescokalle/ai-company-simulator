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
        model_choice: str = Form("auto"),
        token: str = Depends(verify_token),
    ):
        """Onboard a new project and create the virtual company (background job)."""
        try:
            # Determine project source
            if github_url:
                project_source = github_url
            elif project_file:
                upload_dir = Path(__file__).parent.parent.parent / "data" / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                file_path = upload_dir / project_file.filename

                content = await project_file.read()
                file_path.write_bytes(content)
                project_source = str(file_path)
            else:
                raise HTTPException(status_code=400, detail="Either project_file or github_url must be provided")

            offices = [o.strip() for o in optional_offices.split(",") if o.strip()]

            # Resolve the user from the token so the company is scoped to them
            user = await auth_manager.validate_token(token)
            user_id = user["user_id"] if user else None

            # Run onboarding as a background task so /api/company/stop can cancel it
            async def _run():
                return await engine.onboard_project(
                    api_key=api_key,
                    project_source=project_source,
                    project_name=project_name,
                    optional_offices=offices,
                    model_choice=model_choice or "auto",
                    user_id=user_id,
                )

            engine._onboarding_task = asyncio.create_task(_run())

            # Return immediately: progress is streamed over WebSocket/polling
            return {
                "started": True,
                "message": "Creazione azienda avviata. Segui il progresso in tempo reale.",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Onboarding failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/github/upload-key")
    async def upload_private_key(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        private_key: str = Form(...),
    ):
        """Validate and store the GitHub App private key on the server."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Validate the key BEFORE saving anything
        if "PRIVATE KEY" not in private_key:
            return {"success": False, "error": "Formato PEM non valido: header mancante."}

        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            key_obj = serialization.load_pem_private_key(
                private_key.encode("utf-8"), password=None
            )
            if not isinstance(key_obj, rsa.RSAPrivateKey):
                return {"success": False, "error": "La chiave deve essere di tipo RSA."}
            key_size = key_obj.key_size
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Invalid private key uploaded: {e}")
            return {
                "success": False,
                "error": "Chiave privata non valida o corrotta. Rigenera il .pem dal pannello GitHub App.",
            }

        # Only save a validated key
        secrets_dir = Path(__file__).resolve().parent.parent.parent / ".secrets"
        secrets_dir.mkdir(mode=0o700, exist_ok=True)
        key_path = secrets_dir / "github-app-private-key.pem"

        if not private_key.endswith("\n"):
            private_key += "\n"

        try:
            key_path.write_text(private_key)
            key_path.chmod(0o600)
        except Exception as e:
            logger.error(f"Failed to save private key: {e}")
            return {"success": False, "error": "Impossibile salvare la chiave sul server."}

        logger.info(f"GitHub App private key updated (RSA {key_size} bit)")
        return {"success": True, "key_size": key_size, "message": f"Chiave RSA {key_size} bit validata e salvata."}

    @app.post("/api/github/setup")
    async def github_setup(request: dict, token: str = Depends(verify_token)):
        """
        Verify the GitHub App can access a repo and return the install URL if not.
        A GitHub App is not a user, so it cannot be invited as a collaborator:
        it must be installed on the repository.
        """
        try:
            app_id = request.get("app_id")
            owner = request.get("owner")
            repo = request.get("repo")

            if not all([app_id, owner, repo]):
                raise HTTPException(status_code=400, detail="Missing required fields: app_id, owner, repo")

            key_path = Path(__file__).resolve().parent.parent.parent / ".secrets" / "github-app-private-key.pem"
            if not key_path.exists():
                return {
                    "success": False,
                    "error": "Chiave privata non ancora caricata. Carica il file .pem della GitHub App.",
                }

            gh_app = GitHubApp(app_id=str(app_id), private_key=key_path.read_text())
            status = await gh_app.check_installation(str(owner), str(repo))

            if not status.get("installed"):
                return {
                    "success": False,
                    "installed": False,
                    "error": status.get("error"),
                    "install_url": status.get("install_url"),
                }

            if status.get("missing_permissions"):
                return {
                    "success": False,
                    "installed": True,
                    "error": "Permessi mancanti: " + ", ".join(status["missing_permissions"]),
                    "missing_permissions": status["missing_permissions"],
                    "install_url": status.get("install_url"),
                }

            return {
                "success": True,
                "installed": True,
                "message": f"App installata e funzionante su {owner}/{repo}",
                "permissions": status.get("permissions"),
                "installation_id": status.get("installation_id"),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"GitHub setup check failed: {e}")
            return {"success": False, "error": str(e)}

    # ---------- Company control ----------

    @app.post("/api/company/pause")
    async def pause_company(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Pause the running company (all agents stop working)."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        await engine.pause()
        return {"success": True, "paused": True}

    @app.post("/api/company/resume")
    async def resume_company(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Resume a paused company."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        await engine.resume()
        return {"success": True, "paused": False}

    @app.post("/api/company/stop")
    async def stop_company(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Stop the company: halt onboarding, stop all agents, clear state."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return await engine.stop_company()

    @app.get("/api/company/progress")
    async def get_progress(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Current onboarding progress (for polling)."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not engine.progress:
            return {"phase": "idle"}
        return engine.progress.get_state()

    @app.get("/api/companies")
    async def list_companies(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """List all companies owned by the current user."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        companies = await engine.store.list_companies(user["user_id"])
        return {"success": True, "companies": companies}

    @app.get("/api/companies/{company_id}")
    async def get_company(company_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Get one company and load it into the engine (switch)."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        company = await engine.store.get(company_id, user["user_id"])
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        engine.company_id = company["id"]
        engine.project_name = company["name"]
        engine.user_id = user["user_id"]
        return {"success": True, "company": company}

    @app.delete("/api/companies/{company_id}")
    async def delete_company(company_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Delete a company."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        deleted = await engine.store.delete(company_id, user["user_id"])
        if not deleted:
            raise HTTPException(status_code=404, detail="Company not found")
        return {"success": True}

    @app.get("/api/models")
    async def list_models():
        """Available LLM models for the analysis dropdown."""
        return {"success": True, "models": engine.model_selector.list_models()}

    @app.get("/api/settings")
    async def get_settings(credentials: HTTPAuthorizationCredentials = Depends(security)):
        """Get saved settings for the current user (API key is masked)."""
        user = await auth_manager.validate_token(credentials.credentials) if credentials else None
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        settings = await auth_manager.get_settings(user["user_id"])
        # Never return the raw API key to the client
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
        """Save settings for the current user (partial upsert)."""
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
        # Mask the key in the response
        if result.get("settings", {}).get("opencode_api_key"):
            result["settings"]["opencode_api_key"] = "***"
        return result

    @app.post("/api/llm/validate")
    async def validate_llm_key(request: dict, token: str = Depends(verify_token)):
        """Validate an Opencode Zen API key with a real probe request."""
        api_key = request.get("api_key", "")
        if not api_key:
            return {"success": False, "error": "API key mancante"}

        try:
            from llm_client import OpencodeClient
            client = OpencodeClient(api_key=api_key)
            result = await client.get_quota_info()
            if result["valid"]:
                return {
                    "success": True,
                    "message": result.get("error") or "Chiave Opencode valida e funzionante",
                }
            return {"success": False, "error": result.get("error") or "Chiave non valida"}
        except Exception as e:
            return {"success": False, "error": str(e)}

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
