"""
Company Hierarchy - Creates and manages the company structure.
"""
import logging
import uuid
from typing import Any

from .manager import OfficeManagerAgent
from .worker import WorkerAgent

logger = logging.getLogger(__name__)


class CompanyHierarchy:
    """Manages the company organizational structure."""

    def __init__(self, engine: Any, event_bus: Any, vector_store: Any, graph_store: Any):
        self.engine = engine
        self.event_bus = event_bus
        self.vector_store = vector_store
        self.graph_store = graph_store

    async def create_company(
        self,
        project_name: str,
        analysis: dict,
        model_config: dict,
        api_key: str,
        optional_offices: list[str],
    ) -> dict:
        """Create the full company structure from project analysis."""
        company_id = str(uuid.uuid4())[:8]
        logger.info(f"Creating company {company_id} for project {project_name}")

        # Create offices from components
        for component in analysis["components"]:
            await self._create_office(
                company_id=company_id,
                component=component,
                model_config=model_config,
                api_key=api_key,
            )

        # Create optional non-technical offices
        for office_type in optional_offices:
            await self._create_optional_office(
                company_id=company_id,
                office_type=office_type,
                model_config=model_config,
                api_key=api_key,
            )

        return {
            "id": company_id,
            "project_name": project_name,
            "offices": list(self.engine.offices.keys()),
        }

    async def _create_office(
        self,
        company_id: str,
        component: dict,
        model_config: dict,
        api_key: str,
    ):
        """Create an office with manager and workers."""
        office_id = f"office_{component['type']}_{uuid.uuid4().hex[:6]}"
        office_name = component["name"]
        office_type = component["type"]

        logger.info(f"Creating office: {office_name} ({office_type})")

        # Create manager
        manager_id = f"mgr_{office_type}"
        manager = OfficeManagerAgent(
            agent_id=manager_id,
            name=f"{office_name} Manager",
            office_id=office_id,
            office_name=office_name,
            office_type=office_type,
            engine=self.engine,
            model_config=model_config["manager"],
            api_key=api_key,
        )
        self.engine.agents[manager_id] = manager
        await manager.start()

        # Create workers (2-4 per office depending on file count)
        file_count = component.get("file_count", 0)
        worker_count = min(4, max(2, file_count // 10))

        worker_ids = []
        for i in range(worker_count):
            worker_id = f"worker_{office_type}_{i}"
            specialization = self._infer_specialization(component["files"], i)
            worker = WorkerAgent(
                agent_id=worker_id,
                name=f"{specialization} Specialist",
                specialization=specialization,
                engine=self.engine,
                model_config=model_config["worker"],
                api_key=api_key,
            )
            worker.manager_id = manager_id
            worker.position = {
                "x": 100 + (i * 80),
                "y": 500 + (i * 60),
            }
            self.engine.agents[worker_id] = worker
            await worker.start()
            worker_ids.append(worker_id)

        manager.worker_ids = worker_ids

        # Store office info
        self.engine.offices[office_id] = {
            "id": office_id,
            "name": office_name,
            "type": office_type,
            "manager_id": manager_id,
            "worker_ids": worker_ids,
            "file_count": file_count,
        }

        # Update graph
        await self.graph_store.add_office(
            company_id=company_id,
            office_id=office_id,
            office_name=office_name,
            office_type=office_type,
            manager_id=manager_id,
            worker_ids=worker_ids,
        )

        logger.info(f"Office {office_name} created with {worker_count} workers")

    async def _create_optional_office(
        self,
        company_id: str,
        office_type: str,
        model_config: dict,
        api_key: str,
    ):
        """Create a non-technical office (Sales, Marketing, Legal)."""
        office_names = {
            "sales": "Sales",
            "marketing": "Marketing",
            "legal": "Legal",
        }
        office_name = office_names.get(office_type, office_type.title())
        office_id = f"office_{office_type}_{uuid.uuid4().hex[:6]}"

        logger.info(f"Creating optional office: {office_name}")

        # Create manager
        manager_id = f"mgr_{office_type}"
        manager = OfficeManagerAgent(
            agent_id=manager_id,
            name=f"{office_name} Manager",
            office_id=office_id,
            office_name=office_name,
            office_type=office_type,
            engine=self.engine,
            model_config=model_config["manager"],
            api_key=api_key,
        )
        self.engine.agents[manager_id] = manager
        await manager.start()

        # Create 2 workers
        worker_ids = []
        for i in range(2):
            worker_id = f"worker_{office_type}_{i}"
            worker = WorkerAgent(
                agent_id=worker_id,
                name=f"{office_name} Specialist {i+1}",
                specialization=office_type,
                engine=self.engine,
                model_config=model_config["worker"],
                api_key=api_key,
            )
            worker.manager_id = manager_id
            worker.position = {
                "x": 700 + (i * 80),
                "y": 300 + (i * 60),
            }
            self.engine.agents[worker_id] = worker
            await worker.start()
            worker_ids.append(worker_id)

        manager.worker_ids = worker_ids

        self.engine.offices[office_id] = {
            "id": office_id,
            "name": office_name,
            "type": office_type,
            "manager_id": manager_id,
            "worker_ids": worker_ids,
            "file_count": 0,
        }

        await self.graph_store.add_office(
            company_id=company_id,
            office_id=office_id,
            office_name=office_name,
            office_type=office_type,
            manager_id=manager_id,
            worker_ids=worker_ids,
        )

    def _infer_specialization(self, files: list[str], worker_index: int) -> str:
        """Infer worker specialization from file names."""
        if not files:
            return "General"

        file_names = [f.lower() for f in files]
        if any("auth" in f or "login" in f or "user" in f for f in file_names):
            specs = ["Authentication", "API", "UI Components", "Data"]
        elif any("api" in f or "route" in f or "endpoint" in f for f in file_names):
            specs = ["API Routes", "Business Logic", "Database", "Testing"]
        elif any("model" in f or "schema" in f or "migration" in f for f in file_names):
            specs = ["Schema Design", "Queries", "Optimization", "Testing"]
        elif any("docker" in f or "k8s" in f or "deploy" in f for f in file_names):
            specs = ["CI/CD", "Containerization", "Monitoring", "Infrastructure"]
        elif any("test" in f or "spec" in f or "e2e" in f for f in file_names):
            specs = ["Unit Tests", "Integration Tests", "E2E Tests", "Code Review"]
        elif any("mobile" in f or "android" in f or "ios" in f for f in file_names):
            specs = ["iOS", "Android", "React Native", "Flutter"]
        elif any("ml" in f or "ai" in f or "model" in f or "train" in f for f in file_names):
            specs = ["Model Training", "Inference", "Data Pipeline", "MLOps"]
        else:
            specs = ["Frontend", "Backend", "Integration", "Documentation"]

        return specs[worker_index % len(specs)]
