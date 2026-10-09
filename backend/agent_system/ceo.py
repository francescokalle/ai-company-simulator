"""
CEO Agent - The super manager and sole user contact point.
"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)


class CEOAgent(BaseAgent):
    """CEO agent with maximum autonomy."""

    def __init__(self, **kwargs):
        super().__init__(role="ceo", **kwargs)
        self.position = {"x": 400, "y": 100}  # CEO office at top
        self.thoughts = "Ready to lead the company."

    async def _execute_task(self, task: dict):
        """Execute a high-level task by delegating to managers."""
        self.status = "working"
        self.thoughts = f"Processing task: {task.get('description', 'Unknown')}"

        task_type = task.get("type", "general")

        if task_type == "user_message":
            # User sent a message - break it down and delegate
            await self._handle_user_goal(task["content"])
        elif task_type == "delegate":
            # Delegating to a specific manager
            await self._delegate_to_manager(
                task["target_manager"],
                task["instruction"],
            )

    async def _handle_user_goal(self, goal: str):
        """Handle a high-level user goal autonomously."""
        self.thoughts = f"Analyzing goal: {goal[:100]}..."

        # Break down the goal into sub-tasks for each office
        offices = self.engine.offices
        if not offices:
            self.thoughts = "No offices available yet."
            return

        # Distribute work to each office manager
        for office_id, office_info in offices.items():
            manager_id = office_info.get("manager_id")
            if manager_id and manager_id in self.engine.agents:
                instruction = self._create_instruction_for_office(goal, office_info)
                await self.send_message(manager_id, instruction)

        self.thoughts = f"Goal distributed to {len(offices)} offices."

    def _create_instruction_for_office(self, goal: str, office_info: dict) -> str:
        """Create a specific instruction for an office based on the goal."""
        office_name = office_info.get("name", "Unknown")
        office_type = office_info.get("type", "general")

        instructions = {
            "frontend": f"Work on this goal from a frontend perspective: {goal}. "
                        f"Focus on UI/UX, components, and user interaction.",
            "backend": f"Work on this goal from a backend perspective: {goal}. "
                       f"Focus on APIs, business logic, and data processing.",
            "database": f"Work on this goal from a database perspective: {goal}. "
                        f"Focus on schema, queries, and data integrity.",
            "config": f"Work on this goal from a configuration/infrastructure perspective: {goal}. "
                      f"Focus on deployment, settings, and tooling.",
            "mobile": f"Work on this goal from a mobile development perspective: {goal}. "
                      f"Focus on iOS/Android, React Native, Flutter, and mobile UX.",
            "ml": f"Work on this goal from an AI/ML perspective: {goal}. "
                  f"Focus on model training, inference, data pipelines, and ML infrastructure.",
            "devops": f"Work on this goal from a DevOps perspective: {goal}. "
                      f"Focus on CI/CD, Docker, Kubernetes, monitoring, and infrastructure.",
            "security": f"Work on this goal from a security perspective: {goal}. "
                        f"Focus on authentication, authorization, vulnerability management, and best practices.",
            "docs": f"Work on this goal from a documentation perspective: {goal}. "
                    f"Focus on technical docs, API references, guides, and README.",
            "qa": f"Work on this goal from a QA/testing perspective: {goal}. "
                  f"Focus on test automation, quality assurance, and code review.",
            "sales": f"Work on this goal from a sales perspective: {goal}. "
                     f"Focus on customer outreach and revenue strategies.",
            "marketing": f"Work on this goal from a marketing perspective: {goal}. "
                         f"Focus on promotion, branding, and user acquisition.",
            "legal": f"Work on this goal from a legal perspective: {goal}. "
                     f"Focus on compliance, licensing, and risk management.",
        }

        return instructions.get(office_type, f"Work on this goal: {goal}")

    async def _delegate_to_manager(self, manager_id: str, instruction: str):
        """Delegate a task to a specific office manager."""
        if manager_id in self.engine.agents:
            await self.send_message(manager_id, instruction)

    async def _process_message(self, message: str, sender_id: str) -> str:
        """Process messages from managers or workers with real LLM reasoning."""
        self.thoughts = f"Analizzo l'aggiornamento da {sender_id}..."

        system = (
            "Sei il CEO di un'azienda virtuale di sviluppo software. "
            "Hai autonomia totale: prendi decisioni senza chiedere chiarimenti. "
            "Rispondi in italiano, in modo conciso e direzionale. Max 3 frasi."
        )
        prompt = (
            f"Aggiornamento ricevuto da {sender_id}:\n\n{message}\n\n"
            "Rispondi come CEO: dai una direzione, approva, o correggi il tiro."
        )

        response = await self.think(prompt, system=system, max_tokens=512)
        self.thoughts = response[:120]
        return response

    async def _idle_behavior(self):
        """CEO idle behavior - monitor company status."""
        self.status = "idle"
        agent_count = len(self.engine.agents)
        office_count = len(self.engine.offices)
        self.thoughts = f"Monitoring company: {agent_count} agents, {office_count} offices active."
