"""
In-Memory Graph Store - Fallback when Neo4j is unavailable.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class InMemoryGraphStore:
    """Simple in-memory graph store for when Neo4j is not available."""

    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []

    async def initialize(self):
        """Initialize the in-memory store."""
        logger.info("In-memory graph store initialized")

    async def build_project_graph(
        self,
        project_name: str,
        components: list[dict],
        relationships: list[dict],
    ):
        """Build project graph in memory."""
        # Add project node
        self._nodes[f"project_{project_name}"] = {
            "type": "Project",
            "name": project_name,
        }

        # Add component nodes
        for comp in components:
            node_id = f"component_{comp['name']}"
            self._nodes[node_id] = {
                "type": "Component",
                "name": comp["name"],
                "component_type": comp["type"],
            }
            self._edges.append({
                "source": f"project_{project_name}",
                "target": node_id,
                "type": "CONTAINS",
            })

        # Add relationships
        for rel in relationships:
            self._edges.append({
                "source": rel["source"],
                "target": rel["target"],
                "type": rel.get("type", "DEPENDS_ON"),
            })

    async def add_office(
        self,
        company_id: str,
        office_id: str,
        office_name: str,
        office_type: str,
        manager_id: str,
        worker_ids: list[str],
    ):
        """Add office to in-memory graph."""
        # Company node
        self._nodes[f"company_{company_id}"] = {
            "type": "Company",
            "id": company_id,
        }

        # Office node
        self._nodes[f"office_{office_id}"] = {
            "type": "Office",
            "id": office_id,
            "name": office_name,
            "office_type": office_type,
        }
        self._edges.append({
            "source": f"company_{company_id}",
            "target": f"office_{office_id}",
            "type": "HAS_OFFICE",
        })

        # Manager
        self._nodes[f"agent_{manager_id}"] = {
            "type": "Agent",
            "id": manager_id,
            "role": "manager",
        }
        self._edges.append({
            "source": f"office_{office_id}",
            "target": f"agent_{manager_id}",
            "type": "MANAGED_BY",
        })

        # Workers
        for worker_id in worker_ids:
            self._nodes[f"agent_{worker_id}"] = {
                "type": "Agent",
                "id": worker_id,
                "role": "worker",
            }
            self._edges.append({
                "source": f"office_{office_id}",
                "target": f"agent_{worker_id}",
                "type": "HAS_WORKER",
            })

    async def query(self, cypher: str, params: dict = None) -> list[dict]:
        """Simple query - returns all nodes (limited functionality)."""
        return list(self._nodes.values())

    def get_nodes(self) -> list[dict]:
        """Get all nodes."""
        return list(self._nodes.values())

    def get_edges(self) -> list[dict]:
        """Get all edges."""
        return self._edges
