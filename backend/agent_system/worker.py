"""
Worker Agent - Performs actual analysis, coding, and text generation tasks.
"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)


class WorkerAgent(BaseAgent):
    """Worker agent that executes specific tasks."""

    def __init__(self, specialization: str = "general", **kwargs):
        super().__init__(role="worker", **kwargs)
        self.specialization = specialization
        self.position = {"x": 100, "y": 500}

    async def _execute_task(self, task: dict):
        """Execute a specific work task."""
        self.status = "working"
        description = task.get("description", "Unknown task")
        self.thoughts = f"Working on: {description[:80]}..."

        # Simulate work
        await asyncio.sleep(3)

        self.performance["tasks_completed"] += 1
        self.status = "idle"
        self.thoughts = f"Completed: {description[:60]}"

        # Report back to manager
        if hasattr(self, 'manager_id') and self.manager_id in self.engine.agents:
            await self.send_message(self.manager_id, f"Task completed: {description}")

    async def _process_message(self, message: str, sender_id: str) -> str:
        """Process messages from manager using real LLM reasoning."""
        self.thoughts = f"Analizzo il task da {sender_id}..."

        system = (
            f"Sei un worker specializzato in {self.specialization} "
            "in un'azienda virtuale di sviluppo software. "
            "Rispondi in italiano in modo tecnico e operativo. Max 4 frasi."
        )
        prompt = (
            f"Task assegnato da {sender_id}:\n\n{message}\n\n"
            "Descrivi come lo affronterai e quali sono i passi concreti."
        )

        response = await self.think(prompt, system=system, max_tokens=768)

        # Queue the task for execution in the main loop
        self.task_queue.append({
            "type": "work",
            "description": message,
            "from": sender_id,
        })

        self.thoughts = response[:120]
        return response

    async def _idle_behavior(self):
        """Worker idle behavior."""
        self.status = "idle"
        self.thoughts = f"Waiting for tasks. Specialization: {self.specialization}"

    def get_state(self) -> dict:
        state = super().get_state()
        state.update({
            "specialization": self.specialization,
        })
        return state


import asyncio
