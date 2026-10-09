"""
Agent System - All agent types for the virtual company.
"""
import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        engine: Any,
        model_config: dict,
        api_key: str,
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.engine = engine
        self.model_config = model_config
        self.api_key = api_key
        self.status = "idle"  # idle, walking, talking, working, fired
        self.position = {"x": 0, "y": 0}
        self.target_position: Optional[dict] = None
        self.task_queue: list[dict] = []
        self.chat_log: list[dict] = []
        self.thoughts: str = ""
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._aborted = False
        self._llm = None
        self.performance = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_task_time": 0.0,
            "total_messages": 0,
        }

    @property
    def llm(self):
        """Lazily create the LLM client (Opencode Zen)."""
        if self._llm is None:
            from llm_client import OpencodeClient
            self._llm = OpencodeClient(api_key=self.api_key)
        return self._llm

    @property
    def model_name(self) -> str:
        return self.model_config.get("name", "claude-sonnet-4-5")

    async def think(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        """
        Ask the LLM for a response. This is the agent's actual 'brain'.
        Falls back to a deterministic message only if the key is missing.
        """
        if not self.api_key:
            return "[no-api-key] Configura la API key Opcode per abilitare il ragionamento."

        try:
            response = await self.llm.complete(
                prompt=prompt,
                model=self.model_name,
                system=system,
                max_tokens=max_tokens,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Agent {self.name} LLM call failed: {e}")
            return f"[llm-error] {e}"

    async def start(self):
        """Start the agent's main loop."""
        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        logger.info(f"Agent {self.name} ({self.agent_id}) started")

    async def stop(self):
        """Stop the agent."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Agent {self.name} ({self.agent_id}) stopped")

    async def _main_loop(self):
        """Main agent loop. Honors pause/resume."""
        while self._running:
            try:
                # Block while paused (engine-level pause)
                if self.engine and getattr(self.engine, "is_paused", False):
                    await asyncio.sleep(0.5)
                    continue

                if self._aborted:
                    break

                if self.task_queue:
                    task = self.task_queue.pop(0)
                    await self._execute_task(task)
                else:
                    await self._idle_behavior()
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.name} error: {e}")
                await asyncio.sleep(1)

    async def _idle_behavior(self):
        """Default idle behavior - can be overridden."""
        self.status = "idle"
        self.thoughts = "Waiting for tasks..."

    @abstractmethod
    async def _execute_task(self, task: dict):
        """Execute a task - must be implemented by subclasses."""
        pass

    async def receive_message(self, message: str, sender_id: str) -> str:
        """Receive a message from another agent."""
        self.chat_log.append({
            "timestamp": datetime.now().isoformat(),
            "from": sender_id,
            "message": message,
        })
        self.performance["total_messages"] += 1
        return await self._process_message(message, sender_id)

    @abstractmethod
    async def _process_message(self, message: str, sender_id: str) -> str:
        """Process incoming message - must be implemented by subclasses."""
        pass

    async def walk_to(self, target_agent_id: str):
        """Walk to another agent's position."""
        target = self.engine.agents.get(target_agent_id)
        if not target:
            return

        self.status = "walking"
        self.target_position = dict(target.position)
        self.thoughts = f"Walking to {target.name}..."

        # Emit walk event for frontend
        await self.engine.event_bus.emit("agent_walking", {
            "agent_id": self.agent_id,
            "target_id": target_agent_id,
            "from_pos": dict(self.position),
            "to_pos": dict(target.position),
        })

        # Simulate walking (frontend handles animation)
        await asyncio.sleep(2)

        self.position = dict(target.position)
        self.status = "talking"

        # Emit arrival event
        await self.engine.event_bus.emit("agent_arrived", {
            "agent_id": self.agent_id,
            "target_id": target_agent_id,
        })

    async def send_message(self, target_id: str, message: str):
        """Send message to another agent via event bus."""
        # Walk to target first
        await self.walk_to(target_id)

        # Emit communication event
        await self.engine.event_bus.emit("intent_to_communicate", {
            "source": self.agent_id,
            "target": target_id,
            "message": message,
        })

        # Deliver message
        target = self.engine.agents.get(target_id)
        if target:
            response = await target.receive_message(message, self.agent_id)
            self.chat_log.append({
                "timestamp": datetime.now().isoformat(),
                "to": target_id,
                "message": message,
                "response": response,
            })
            return response
        return None

    def get_state(self) -> dict:
        """Get current agent state for frontend."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "position": self.position,
            "thoughts": self.thoughts,
            "task_count": len(self.task_queue),
            "performance": self.performance,
        }

    def get_full_state(self) -> dict:
        """Get full agent state including logs."""
        return {
            **self.get_state(),
            "task_queue": self.task_queue,
            "chat_log": self.chat_log[-50:],  # Last 50 messages
            "model": self.model_config,
        }
