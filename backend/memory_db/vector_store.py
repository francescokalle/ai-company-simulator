"""
Vector Store - ChromaDB wrapper for semantic code search.
"""
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB-based vector store for project knowledge."""

    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None

    async def initialize(self):
        """Initialize ChromaDB."""
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._client.get_or_create_collection(
                name="project_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB initialized")
        except ImportError:
            logger.warning("ChromaDB not available, using in-memory fallback")
            self._collection = None

    async def ingest_project(
        self,
        project_name: str,
        files: list[dict],
        components: list[dict],
    ):
        """Ingest project files into the vector store."""
        if not self._collection:
            logger.warning("Vector store not available, skipping ingestion")
            return

        documents = []
        metadatas = []
        ids = []

        for i, file in enumerate(files):
            # Chunk large files
            content = file["content"]
            chunks = [content[j:j+1000] for j in range(0, len(content), 1000)]
            for k, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({
                    "project": project_name,
                    "file_path": file["path"],
                    "language": file["language"],
                    "chunk": k,
                })
                ids.append(f"{project_name}_{i}_{k}")

        if documents:
            self._collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info(f"Ingested {len(document)} chunks from {len(files)} files")

    async def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Semantic search over project knowledge."""
        if not self._collection:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        return [
            {
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["documents"][0]))
        ]
