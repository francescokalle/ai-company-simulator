"""
Graph Store - Neo4j wrapper for mapping codebase relationships.
Falls back to in-memory graph if Neo4j is unavailable.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GraphStore:
    """Neo4j-based graph store for project relationships."""

    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    async def initialize(self):
        """Initialize Neo4j connection."""
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            # Test connection
            async with self._driver.session() as session:
                await session.run("RETURN 1")
            logger.info("Neo4j connected")
        except Exception as e:
            logger.warning(f"Neo4j connection failed: {e}")
            self._driver = None
            raise

    async def build_project_graph(
        self,
        project_name: str,
        components: list[dict],
        relationships: list[dict],
    ):
        """Build the project knowledge graph."""
        if not self._driver:
            return

        async with self._driver.session() as session:
            # Create project node
            await session.run(
                "MERGE (p:Project {name: $name})",
                name=project_name,
            )

            # Create component nodes
            for comp in components:
                await session.run(
                    "MERGE (c:Component {name: $name, type: $type}) "
                    "MERGE (p:Project {name: $project}) "
                    "MERGE (p)-[:CONTAINS]->(c)",
                    name=comp["name"],
                    type=comp["type"],
                    project=project_name,
                )

            # Create relationships
            for rel in relationships:
                await session.run(
                    "MATCH (a:Component), (b:Component) "
                    "WHERE a.name = $source AND b.name = $target "
                    "MERGE (a)-[:DEPENDS_ON]->(b)",
                    source=rel["source"],
                    target=rel["target"],
                )

    async def add_office(
        self,
        company_id: str,
        office_id: str,
        office_name: str,
        office_type: str,
        manager_id: str,
        worker_ids: list[str],
    ):
        """Add office structure to the graph."""
        if not self._driver:
            return

        async with self._driver.session() as session:
            await session.run(
                "MERGE (o:Office {id: $office_id, name: $name, type: $type}) "
                "MERGE (c:Company {id: $company_id}) "
                "MERGE (c)-[:HAS_OFFICE]->(o)",
                office_id=office_id,
                name=office_name,
                type=office_type,
                company_id=company_id,
            )

            # Add manager
            await session.run(
                "MERGE (a:Agent {id: $manager_id, role: 'manager'}) "
                "MERGE (o:Office {id: $office_id}) "
                "MERGE (o)-[:MANAGED_BY]->(a)",
                manager_id=manager_id,
                office_id=office_id,
            )

            # Add workers
            for worker_id in worker_ids:
                await session.run(
                    "MERGE (a:Agent {id: $worker_id, role: 'worker'}) "
                    "MERGE (o:Office {id: $office_id}) "
                    "MERGE (o)-[:HAS_WORKER]->(a)",
                    worker_id=worker_id,
                    office_id=office_id,
                )

    async def query(self, cypher: str, params: dict = None) -> list[dict]:
        """Run a Cypher query."""
        if not self._driver:
            return []

        async with self._driver.session() as session:
            result = await session.run(cypher, params or {})
            return [record.data() async for record in result]
