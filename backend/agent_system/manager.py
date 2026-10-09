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
        """Process messages from CEO or workers using real LLM reasoning."""
        self.thoughts = f"Analizzo il messaggio da {sender_id}..."

        system = (
            f"Sei il manager dell'ufficio {self.office_name} in un'azienda virtuale di sviluppo software. "
            "Ricevi istruzioni dal CEO e rispondi in italiano, in modo operativo e conciso. "
            "Il tuo compito è scomporre il lavoro in task concreti per i tuoi worker."
        )
        prompt = (
            f"Mittente: {sender_id}\n"
            f"Messaggio:\n{message}\n\n"
            "Rispondi come manager: conferma ricezione e indica come procederai. Max 3 frasi."
        )

        response = await self.think(prompt, system=system, max_tokens=512)
        self.thoughts = response[:120]

        # If the CEO gave an instruction, queue it as a task to break down
        if sender_id == "ceo":
            self.task_queue.append({
                "type": "delegate",
                "description": message,
                "from": sender_id,
            })

        return response

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
