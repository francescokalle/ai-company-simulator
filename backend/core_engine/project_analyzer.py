"""
Project Analyzer - Scans and analyzes uploaded codebases.
"""
import os
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Any

import logging

logger = logging.getLogger(__name__)


class ProjectAnalyzer:
    """Analyzes a project to extract components, files, and relationships."""

    async def analyze(self, source: str) -> dict[str, Any]:
        """
        Analyze a project from a zip file or git URL.
        
        Args:
            source: Path to zip file or git URL.
            
        Returns:
            Analysis dict with files, components, relationships, complexity.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = await self._fetch_project(source, tmpdir)
            files = self._scan_files(project_path)
            components = self._identify_components(project_path, files)
            relationships = self._extract_relationships(project_path, files, components)
            complexity = self._compute_complexity(files)

            return {
                "files": files,
                "components": components,
                "relationships": relationships,
                "total_files": len(files),
                "complexity_score": complexity,
                "component_count": len(components),
            }

    async def _fetch_project(self, source: str, dest: str) -> Path:
        """Fetch project from zip or git."""
        if source.endswith(".zip"):
            with zipfile.ZipFile(source, "r") as zf:
                zf.extractall(dest)
            return Path(dest)
        elif source.startswith("http") and ".git" in source:
            subprocess.run(
                ["git", "clone", "--depth", "1", source, dest],
                check=True,
                capture_output=True,
            )
            return Path(dest)
        else:
            # Assume it's a local path
            return Path(source)

    def _scan_files(self, root: Path) -> list[dict]:
        """Scan all relevant source files."""
        files = []
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
        source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ".c", ".cpp", ".h"}

        for path in root.rglob("*"):
            if any(skip in path.parts for skip in skip_dirs):
                continue
            if path.is_file() and path.suffix in source_exts:
                try:
                    content = path.read_text(errors="ignore")
                    rel_path = str(path.relative_to(root))
                    files.append({
                        "path": rel_path,
                        "content": content[:50000],  # Cap file size
                        "size": len(content),
                        "language": self._detect_language(path.suffix),
                    })
                except Exception as e:
                    logger.warning(f"Could not read {path}: {e}")

        return files

    def _identify_components(self, root: Path, files: list[dict]) -> list[dict]:
        """Identify major project components (frontend, backend, etc.)."""
        components = []

        # Detect by directory structure
        frontend_indicators = {"src", "client", "frontend", "web", "ui", "pages", "components"}
        backend_indicators = {"server", "api", "backend", "app", "core", "lib"}
        db_indicators = {"db", "database", "migrations", "models", "schema"}
        config_indicators = {"config", "settings", "env"}
        mobile_indicators = {"mobile", "android", "ios", "react-native", "flutter", "ionic"}
        ml_indicators = {"ml", "ai", "machine-learning", "deep-learning", "model", "training", "inference"}
        devops_indicators = {"docker", "k8s", "kubernetes", "terraform", "ansible", "ci", "cd", "deploy"}
        security_indicators = {"security", "auth", "oauth", "jwt", "encryption", "vault"}
        docs_indicators = {"docs", "documentation", "wiki", "guides", "readme"}
        test_indicators = {"test", "tests", "spec", "e2e", "cypress", "jest", "pytest"}

        frontend_files = [f for f in files if any(ind in f["path"].lower() for ind in frontend_indicators)]
        backend_files = [f for f in files if any(ind in f["path"].lower() for ind in backend_indicators)]
        db_files = [f for f in files if any(ind in f["path"].lower() for ind in db_indicators)]
        config_files = [f for f in files if any(ind in f["path"].lower() for ind in config_indicators)]
        mobile_files = [f for f in files if any(ind in f["path"].lower() for ind in mobile_indicators)]
        ml_files = [f for f in files if any(ind in f["path"].lower() for ind in ml_indicators)]
        devops_files = [f for f in files if any(ind in f["path"].lower() for ind in devops_indicators)]
        security_files = [f for f in files if any(ind in f["path"].lower() for ind in security_indicators)]
        docs_files = [f for f in files if any(ind in f["path"].lower() for ind in docs_indicators)]
        test_files = [f for f in files if any(ind in f["path"].lower() for ind in test_indicators)]

        if frontend_files:
            components.append({
                "name": "Frontend",
                "type": "frontend",
                "files": [f["path"] for f in frontend_files],
                "file_count": len(frontend_files),
            })
        if backend_files:
            components.append({
                "name": "Backend",
                "type": "backend",
                "files": [f["path"] for f in backend_files],
                "file_count": len(backend_files),
            })
        if db_files:
            components.append({
                "name": "Database",
                "type": "database",
                "files": [f["path"] for f in db_files],
                "file_count": len(db_files),
            })
        if config_files:
            components.append({
                "name": "Configuration",
                "type": "config",
                "files": [f["path"] for f in config_files],
                "file_count": len(config_files),
            })
        if mobile_files:
            components.append({
                "name": "Mobile",
                "type": "mobile",
                "files": [f["path"] for f in mobile_files],
                "file_count": len(mobile_files),
            })
        if ml_files:
            components.append({
                "name": "AI/ML",
                "type": "ml",
                "files": [f["path"] for f in ml_files],
                "file_count": len(ml_files),
            })
        if devops_files:
            components.append({
                "name": "DevOps",
                "type": "devops",
                "files": [f["path"] for f in devops_files],
                "file_count": len(devops_files),
            })
        if security_files:
            components.append({
                "name": "Security",
                "type": "security",
                "files": [f["path"] for f in security_files],
                "file_count": len(security_files),
            })
        if docs_files:
            components.append({
                "name": "Documentation",
                "type": "docs",
                "files": [f["path"] for f in docs_files],
                "file_count": len(docs_files),
            })
        if test_files:
            components.append({
                "name": "QA/Testing",
                "type": "qa",
                "files": [f["path"] for f in test_files],
                "file_count": len(test_files),
            })

        # If no components found, create a generic one
        if not components and files:
            components.append({
                "name": "Core",
                "type": "core",
                "files": [f["path"] for f in files],
                "file_count": len(files),
            })

        return components

    def _extract_relationships(self, root: Path, files: list[dict], components: list[dict]) -> list[dict]:
        """Extract import/dependency relationships between files."""
        relationships = []
        # Simple heuristic: if file A imports from file B, create a relationship
        for f in files:
            content = f["content"]
            for other in files:
                if f["path"] == other["path"]:
                    continue
                # Check for import patterns
                module_name = Path(other["path"]).stem
                if module_name in content:
                    relationships.append({
                        "source": f["path"],
                        "target": other["path"],
                        "type": "imports",
                    })
        return relationships

    def _compute_complexity(self, files: list[dict]) -> float:
        """Compute a simple complexity score."""
        if not files:
            return 0.0
        total_lines = sum(f["size"] for f in files)
        unique_languages = len(set(f["language"] for f in files))
        # Simple heuristic: more files + more languages = more complex
        score = min(1.0, (len(files) / 500) * 0.5 + (unique_languages / 10) * 0.5)
        return round(score, 2)

    def _detect_language(self, ext: str) -> str:
        """Detect programming language from file extension."""
        mapping = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
            ".rs": "rust", ".java": "java", ".rb": "ruby",
            ".php": "php", ".cs": "csharp", ".c": "c",
            ".cpp": "cpp", ".h": "c",
        }
        return mapping.get(ext, "unknown")
