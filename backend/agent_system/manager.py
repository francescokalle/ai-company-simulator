"""
Office Manager Agent - Manages a team of worker agents.
"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)


class OfficeManagerAgent(BaseAgent):
    """Manages workers in a specific office."""

    def __init__(self, office_id: str, office_name: str, office_type: str, **kwargs):
        super().__init__(role="manager", **kwargs)
        self.office_id = office_id
        self.office_name = office_name
        self.office_type = office_type
        self.worker_ids: list[str] = []
        self.position = {"x": 200, "y": 300}

    async def _execute_task(self, task: dict):
        """Break down tasks and assign to workers."""
        self.status = "working"
        description = task.get("description", "Unknown task")
        self.thoughts = f"Breaking down task: {description[:80]}..."

        # Create sub-tasks for workers
        sub_tasks = self._break_down_task(description)

        for i, sub_task in enumerate(sub_tasks):
            if self.worker_ids:
                worker_id = self.worker_ids[i % len(self.worker_ids)]
                if worker_id in self.engine.agents:
                    await self.send_message(worker_id, sub_task)

        self.thoughts = f"Distributed {len(sub_tasks)} sub-tasks to {len(self.worker_ids)} workers."

    def _break_down_task(self, description: str) -> list[str]:
        """Break a high-level task into worker-level sub-tasks."""
        # Simple breakdown - in production this would use LLM
        return [
            f"Analyze requirements for: {description}",
            f"Implement solution for: {description}",
            f"Test and validate: {description}",
        ]

    async def _process_message(self, message: str, sender_id: str) -> str:
        """Process messages from CEO or workers."""
        self.thoughts = f"Received from {sender_id}: {message[:80]}..."

        if sender_id == "ceo":
            # CEO instruction - queue as task
            self.task_queue.append({
                "type": "delegate",
                "description": message,
                "from": sender_id,
            })
            return f"Received instruction from CEO. Breaking down into tasks for {len(self.worker_ids)} workers."

        # Worker update
        if "completed" in message.lower():
            self.performance["tasks_completed"] += 1
            return "Great work! Keep it up."

        return "Understood. Continue with your assigned tasks."

    async def _idle_behavior(self):
        """Manager idle behavior."""
        self.status = "idle"
        self.thoughts = f"Managing {self.office_name} office. {len(self.worker_ids)} workers active."

    def get_state(self) -> dict:
        state = super().get_state()
        state.update({
            "office_id": self.office_id,
            "office_name": self.office_name,
            "office_type": self.office_type,
            "worker_count": len(self.worker_ids),
            "workers": self.worker_ids,
        })
        return state
