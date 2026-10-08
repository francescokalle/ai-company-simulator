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
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing token")
        # Validate via auth manager
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            auth_manager.validate_token(credentials.credentials)
        )
        if not result:
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
    async def github_invite(request: dict):
        """Invite a collaborator via GitHub App."""
        try:
            app_id = request.get("app_id")
            private_key = request.get("private_key")
            installation_id = request.get("installation_id")
            owner = request.get("owner")
            repo = request.get("repo")
            collaborator = request.get("collaborator")

            if not all([app_id, private_key, installation_id, owner, repo, collaborator]):
                raise HTTPException(status_code=400, detail="Missing required fields")

            gh_app = GitHubApp(app_id=app_id, private_key=private_key)
            token = await gh_app.get_installation_token(int(installation_id))
            result = await gh_app.invite_collaborator(token, owner, repo, collaborator)

            if result["success"]:
                return {"success": True, "message": f"Invitation sent to {collaborator}"}
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
        except Exception as e:
            logger.error(f"GitHub invite failed: {e}")
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
        if not token or token not in active_tokens:
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

        # Subscribe to engine events
        self.engine.event_bus.subscribe("agent_walking", self._create_handler("agent_walking"))
        self.engine.event_bus.subscribe("agent_arrived", self._create_handler("agent_arrived"))
        self.engine.event_bus.subscribe("intent_to_communicate", self._create_handler("intent_to_communicate"))
        self.engine.event_bus.subscribe("agent_fired", self._create_handler("agent_fired"))
        self.engine.event_bus.subscribe("request_new_agent", self._create_handler("request_new_agent"))

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
