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
        """Process messages from manager."""
        self.thoughts = f"Received task from {sender_id}: {message[:80]}..."

        # Queue the task
        self.task_queue.append({
            "type": "work",
            "description": message,
            "from": sender_id,
        })

        return f"Task queued: {message[:60]}"

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
