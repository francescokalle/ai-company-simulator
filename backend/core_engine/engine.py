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
        self._lock = asyncio.Lock()

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

        self._running = True
        logger.info("Company Engine initialized successfully")

    async def shutdown(self):
        """Graceful shutdown."""
        self._running = False
        if self.event_bus:
            await self.event_bus.stop()
        logger.info("Company Engine shut down")

    async def onboard_project(
        self,
        api_key: str,
        project_source: str,
        project_name: str,
        optional_offices: list[str] | None = None,
        github_token: str | None = None,
    ) -> dict:
        """
        Onboard a new project: analyze, create offices, spawn agents.
        Supports both zip upload and GitHub repo URL.
        """
        logger.info(f"Onboarding project: {project_name}")

        # 1. Analyze project
        analysis = await self.analyzer.analyze(project_source)
        logger.info(f"Project analysis complete: {analysis['component_count']} components")

        # 2. Select models based on complexity
        model_config = self.model_selector.select_models(
            project_size=analysis["total_files"],
            complexity_score=analysis["complexity_score"],
        )
        logger.info(f"Selected models: {model_config}")

        # 3. Store project knowledge in vector DB
        await self.vector_store.ingest_project(
            project_name=project_name,
            files=analysis["files"],
            components=analysis["components"],
        )

        # 4. Build knowledge graph
        await self.graph_store.build_project_graph(
            project_name=project_name,
            components=analysis["components"],
            relationships=analysis["relationships"],
        )

        # 5. Create company structure
        company = await self.hierarchy.create_company(
            project_name=project_name,
            analysis=analysis,
            model_config=model_config,
            api_key=api_key,
            optional_offices=optional_offices or [],
        )

        # Enforce agent cap - prevent exceeding MAX_AGENTS
        if len(self.agents) > self.MAX_AGENTS:
            logger.warning(
                f"Agent cap exceeded: {len(self.agents)}/{self.MAX_AGENTS}. "
                f"Stopping agent startup."
            )
            self._running = False
            return {
                "error": "agent_cap_exceeded",
                "detail": f"Project would create {len(self.agents)} agents, exceeding the {self.MAX_AGENTS} limit.",
                "agent_count": len(self.agents),
                "max_agents": self.MAX_AGENTS,
            }

        # 6. Spawn CEO
        ceo = CEOAgent(
            agent_id="ceo",
            name="CEO",
            engine=self,
            model_config=model_config["ceo"],
            api_key=api_key,
        )
        self.agents["ceo"] = ceo
        await ceo.start()

        # 7. Spawn Efficiency/HR office
        efficiency = EfficiencyAgent(
            agent_id="efficiency",
            name="Efficiency Manager",
            engine=self,
            model_config=model_config["efficiency"],
            api_key=api_key,
        )
        self.agents["efficiency"] = efficiency
        await efficiency.start()

        # 8. Generate GitHub invite URL if repo URL provided
        github_invite_url = None
        if project_source.startswith("http") and "github.com" in project_source:
            github_invite_url = f"https://github.com/{project_source.split('github.com/')[1]}/invitations"

        logger.info(f"Company created with {len(self.agents)} agents and {len(self.offices)} offices")

        return {
            "company_id": company["id"],
            "project_name": project_name,
            "offices": list(self.offices.keys()),
            "agent_count": len(self.agents),
            "analysis": analysis,
            "github_invite_url": github_invite_url,
        }

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
