"""
AI Virtual Company Simulator - Main Entry Point
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add backend/ to sys.path so internal imports work
sys.path.insert(0, str(Path(__file__).parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from web_server.server import create_app
from core_engine.engine import CompanyEngine

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    engine = CompanyEngine(data_dir=data_dir)
    await engine.initialize()

    app = create_app(engine)

    import uvicorn
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=60,
    )
    server = uvicorn.Server(config)
    logger.info("🚀 AI Virtual Company Simulator starting on port 8000")
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
