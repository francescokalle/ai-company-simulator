"""
Core Engine - Orchestrates the entire virtual company simulation.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from agent_system import CEOAgent, OfficeManagerAgent, WorkerAgent, EfficiencyAgent
from agent_system.hierarchy import CompanyHierarchy
from memory_db.vector_store import VectorStore
from memory_db.graph_store import GraphStore
from memory_db.memory_graph import InMemoryGraphStore
from event_bus.bus import EventBus
from core_engine.project_analyzer import ProjectAnalyzer
from core_engine.model_selector import ModelSelector
from core_engine.progress import ProgressTracker
from core_engine.company_store import CompanyStore

logger = logging.getLogger(__name__)


class CompanyEngine:
    """Main engine that orchestrates the virtual company."""

    MAX_AGENTS = 50  # Hard cap to prevent OOM

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.event_bus: Optional[EventBus] = None
        self.vector_store: Optional[VectorStore] = None
        self.graph_store: Optional[GraphStore] = None
        self.hierarchy: Optional[CompanyHierarchy] = None
        self.analyzer = ProjectAnalyzer()
        self.model_selector = ModelSelector()
        self.agents: dict[str, any] = {}
        self.offices: dict[str, any] = {}
        self._running = False
        self._paused = False
        self._lock = asyncio.Lock()
        self.store = CompanyStore()
        self.progress: Optional[ProgressTracker] = None
        self.company_id: Optional[str] = None
        self.project_name: Optional[str] = None
        self.user_id: Optional[int] = None
        self.selected_tier: str = "auto"
        self.analysis_model: Optional[str] = None
        self._onboarding_task: Optional[asyncio.Task] = None

    # ---------- pause / resume ----------

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def pause(self):
        """Pause all agents."""
        self._paused = True
        if self.progress:
            self.progress.pause()
        for agent in self.agents.values():
            agent.status = "paused"
        await self._emit("company_paused", {"company_id": self.company_id})
        logger.info("Company paused")

    async def resume(self):
        """Resume all agents."""
        self._paused = False
        if self.progress:
            self.progress.resume()
        for agent in self.agents.values():
            if agent.status == "paused":
                agent.status = "idle"
        # Persist running status
        if self.store and self.company_id and self.user_id:
            await self.store.set_status(self.company_id, self.user_id, "running")
        await self._emit("company_resumed", {"company_id": self.company_id})
        logger.info("Company resumed")

    async def _emit(self, event_type: str, data: dict):
        """Broadcast an event on the bus."""
        if self.event_bus:
            await self.event_bus.emit(event_type, data)

    async def _emit_progress(self, event_type: str, data: dict):
        """Progress events also go on the bus so the frontend can follow."""
        if self.event_bus:
            await self.event_bus.emit(event_type, data)

    async def initialize(self):
        """Initialize all subsystems."""
        logger.info("Initializing Company Engine...")

        # Event bus
        self.event_bus = EventBus()
        await self.event_bus.start()

        # Memory systems
        self.vector_store = VectorStore(persist_dir=self.data_dir / "chroma")
        await self.vector_store.initialize()

        self.graph_store = GraphStore(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password"
        )
        # Fallback to in-memory graph if Neo4j unavailable
        try:
            await self.graph_store.initialize()
        except Exception:
            logger.warning("Neo4j unavailable, using in-memory graph store")
            from memory_db.memory_graph import InMemoryGraphStore
            self.graph_store = InMemoryGraphStore()
            await self.graph_store.initialize()

        # Company hierarchy
        self.hierarchy = CompanyHierarchy(
            engine=self,
            event_bus=self.event_bus,
            vector_store=self.vector_store,
            graph_store=self.graph_store,
        )

        # Progress tracker + company store
        self.progress = ProgressTracker(emit=self._emit_progress)
        self.store = CompanyStore()
        await self.store.initialize()

        self._running = True
        logger.info("Company Engine initialized successfully")

    async def shutdown(self):
        """Graceful shutdown."""
        self._running = False
        if self.event_bus:
            await self.event_bus.stop()
        logger.info("Company Engine shut down")

    async def stop_company(self) -> dict:
        """
        Stop the running company: cancel onboarding, stop every agent,
        clear in-memory state and mark the company stopped.
        """
        # Abort an in-progress onboarding pipeline
        if self.progress:
            self.progress.abort()
        if self._onboarding_task and not self._onboarding_task.done():
            self._onboarding_task.cancel()
            try:
                await self._onboarding_task
            except (asyncio.CancelledError, Exception):
                pass
        self._onboarding_task = None

        # Stop all agents for real
        for agent in list(self.agents.values()):
            try:
                await agent.stop()
            except Exception as e:
                logger.error(f"Error stopping agent {agent.agent_id}: {e}")

        company_id = self.company_id
        user_id = self.user_id

        # Reset in-memory state so get_company_state() is empty
        self.agents.clear()
        self.offices.clear()
        self._paused = False
        self._running = False
        self.company_id = None
        self.project_name = None
        self.user_id = None

        # Persist status
        if company_id and user_id and self.store:
            await self.store.set_status(company_id, user_id, "stopped")

        # Reset progress tracker
        if self.progress:
            self.progress.reset()

        await self._emit("company_stopped", {"company_id": company_id})
        logger.info("Company stopped and state cleared")
        return {"success": True, "stopped": company_id}

    async def onboard_project(
        self,
        api_key: str,
        project_source: str,
        project_name: str,
        optional_offices: list[str] | None = None,
        model_choice: str = "auto",
        user_id: int | None = None,
        github_token: str | None = None,
    ) -> dict:
        """
        Onboard a new project: analyze, create offices, spawn agents.
        Supports zip upload and GitHub repo URL.
        Emits progress events at every phase. Pausable and abortable.
        Ends with all agents PAUSED.
        """
        logger.info(f"Onboarding project: {project_name}")

        self.user_id = user_id
        self.project_name = project_name
        self._paused = False
        self.progress.reset()

        try:
            # ---- Step 1: fetch project ----
            await self.progress.start_step("fetch", "Scaricamento del progetto", project_source)
            await self.progress.wait_if_paused()
            import tempfile
            from pathlib import Path as _Path
            tmpdir = tempfile.mkdtemp(prefix=f"company_{project_name}_")
            project_path = await self.analyzer._fetch_project(project_source, tmpdir)

            # ---- Step 2: scan files (streamed) ----
            await self.progress.start_step("scan", "Scansione dei file sorgente", str(project_path))
            await self.progress.wait_if_paused()
            files = self.analyzer._scan_files(_Path(project_path))
            for i, f in enumerate(files):
                if i % 25 == 0:  # throttle updates
                    await self.progress.update_detail(f"{i}/{len(files)} file: {f['path']}")
                    await self.progress.wait_if_paused()

            # ---- Step 3: identify components ----
            await self.progress.start_step(
                "components", "Identificazione dei componenti",
                f"{len(files)} file trovati"
            )
            await self.progress.wait_if_paused()
            components = self.analyzer._identify_components(_Path(project_path), files)

            # ---- Step 4: extract relationships ----
            await self.progress.start_step(
                "relationships", "Analisi delle dipendenze",
                f"{len(components)} componenti"
            )
            await self.progress.wait_if_paused()
            relationships = self.analyzer._extract_relationships(_Path(project_path), files, components)

            complexity = self.analyzer._compute_complexity(files)
            analysis = {
                "files": files,
                "components": components,
                "relationships": relationships,
                "total_files": len(files),
                "complexity_score": complexity,
                "component_count": len(components),
            }

            # ---- Model selection (user choice or auto) ----
            if model_choice and model_choice != "auto":
                model_config = self.model_selector.select_fixed_model(model_choice)
                logger.info(f"Models forced by user: {model_config}")
            else:
                model_config = self.model_selector.select_models(
                    project_size=len(files),
                    complexity_score=complexity,
                )
                logger.info(f"Models auto-selected: {model_config}")

            # ---- Step 5: build memory ----
            await self.progress.start_step(
                "memory", "Costruzione della memoria di progetto",
                "Vector store + knowledge graph"
            )
            await self.progress.wait_if_paused()
            await self.vector_store.ingest_project(
                project_name=project_name,
                files=analysis["files"],
                components=analysis["components"],
            )
            await self.graph_store.build_project_graph(
                project_name=project_name,
                components=analysis["components"],
                relationships=analysis["relationships"],
            )

            # ---- Step 6: create offices and agents ----
            await self.progress.start_step(
                "offices", "Creazione uffici e agenti",
                f"{len(components)} uffici tecnici"
            )
            await self.progress.wait_if_paused()
            company = await self.hierarchy.create_company(
                project_name=project_name,
                analysis=analysis,
                model_config=model_config,
                api_key=api_key,
                optional_offices=optional_offices or [],
            )

            # Enforce agent cap
            if len(self.agents) > self.MAX_AGENTS:
                logger.warning(f"Agent cap exceeded: {len(self.agents)}/{self.MAX_AGENTS}")
                await self.stop_company()
                return {
                    "error": "agent_cap_exceeded",
                    "detail": f"Il progetto creerebbe {len(self.agents)} agenti, oltre il limite di {self.MAX_AGENTS}.",
                    "agent_count": len(self.agents),
                    "max_agents": self.MAX_AGENTS,
                }

            # ---- Step 7: spawn leadership ----
            await self.progress.start_step("leadership", "Nomina CEO e ufficio Efficiency")
            await self.progress.wait_if_paused()
            ceo = CEOAgent(
                agent_id="ceo", name="CEO", engine=self,
                model_config=model_config["ceo"], api_key=api_key,
            )
            self.agents["ceo"] = ceo
            await ceo.start()

            efficiency = EfficiencyAgent(
                agent_id="efficiency", name="Efficiency Manager", engine=self,
                model_config=model_config["efficiency"], api_key=api_key,
            )
            self.agents["efficiency"] = efficiency
            await efficiency.start()

            # ---- Step 8: finalize (persist + pause) ----
            await self.progress.start_step("finalize", "Salvataggio dell'azienda")
            company_id = company["id"]
            self.company_id = company_id

            if self.store and user_id:
                await self.store.save(
                    company_id=company_id,
                    user_id=user_id,
                    name=project_name,
                    source=project_source,
                    status="paused",
                    state={
                        "offices": list(self.offices.keys()),
                        "agent_ids": list(self.agents.keys()),
                        "models": model_config,
                        "analysis_summary": {
                            "total_files": len(files),
                            "components": len(components),
                            "complexity": complexity,
                        },
                    },
                )

            await self.progress.complete("Azienda creata. Simulazione in pausa.")

            # End PAUSED as requested
            await self.pause()

            await self._emit("company_created", {
                "company_id": company_id,
                "name": project_name,
                "agent_count": len(self.agents),
                "paused": True,
            })

            logger.info(
                f"Company {company_id} created with {len(self.agents)} agents, "
                f"{len(self.offices)} offices, paused"
            )

            return {
                "company_id": company_id,
                "project_name": project_name,
                "offices": list(self.offices.keys()),
                "agent_count": len(self.agents),
                "models": model_config,
                "paused": True,
                "analysis": {
                    "total_files": analysis["total_files"],
                    "component_count": analysis["component_count"],
                    "complexity_score": analysis["complexity_score"],
                    "components": [c["name"] for c in analysis["components"]],
                },
            }

        except asyncio.CancelledError:
            logger.info("Onboarding cancelled by user")
            await self.progress.update_message("Creazione annullata")
            await self.stop_company()
            return {"error": "cancelled", "detail": "Creazione annullata dall'utente"}
        except Exception as e:
            logger.error(f"Onboarding failed: {e}", exc_info=True)
            await self.progress.fail(str(e))
            return {"error": "onboarding_failed", "detail": str(e)}

    async def handle_user_message(self, message: str) -> str:
        """Route user message to CEO."""
        ceo = self.agents.get("ceo")
        if not ceo:
            return "No CEO available. Please onboard a project first."
        return await ceo.receive_message(message, "user")

    async def get_company_state(self) -> dict:
        """Get full company state for frontend."""
        return {
            "agents": {
                aid: agent.get_state()
                for aid, agent in self.agents.items()
            },
            "offices": {
                oid: office
                for oid, office in self.offices.items()
            },
            "agent_count": len(self.agents),
            "max_agents": self.MAX_AGENTS,
            "running": self._running,
            "paused": self._paused,
            "company_id": self.company_id,
            "company_name": self.project_name,
            "progress": self.progress.get_state() if self.progress else None,
        }

    async def get_agent_details(self, agent_id: str) -> dict:
        """Get detailed info about a specific agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}
        return agent.get_full_state()

    def can_spawn_agent(self) -> bool:
        """Check if we can spawn more agents (under the cap)."""
        return len(self.agents) < self.MAX_AGENTS
