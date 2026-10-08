"""
Efficiency Agent - Monitors and optimizes company performance.
"""
import asyncio
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)


class EfficiencyAgent(BaseAgent):
    """Monitors company performance and optimizes agent allocation."""

    def __init__(self, **kwargs):
        super().__init__(role="efficiency", **kwargs)
        self.position = {"x": 600, "y": 100}
        self.monitoring_interval = 30  # seconds
        self.performance_history: list[dict] = []
        self._monitor_task: asyncio.Task | None = None

    async def start(self):
        """Start the agent and monitoring loop."""
        await super().start()
        self._monitor_task = asyncio.create_task(self._monitoring_loop())

    async def stop(self):
        """Stop the agent and monitoring loop."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await super().stop()

    async def _monitoring_loop(self):
        """Continuously monitor company performance."""
        while self._running:
            try:
                await self._analyze_performance()
                await asyncio.sleep(self.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(5)

    async def _analyze_performance(self):
        """Analyze company performance and take optimization actions."""
        agents = self.engine.agents
        if not agents:
            return

        metrics = {
            "timestamp": asyncio.get_event_loop().time(),
            "total_agents": len(agents),
            "active_tasks": sum(len(a.task_queue) for a in agents.values()),
            "avg_completion_rate": self._compute_avg_completion_rate(agents),
            "bottlenecks": self._identify_bottlenecks(agents),
        }
        self.performance_history.append(metrics)

        # Take action if needed
        if metrics["bottlenecks"]:
            await self._resolve_bottlenecks(metrics["bottlenecks"])

        # Check if we need more agents (under the cap)
        if metrics["active_tasks"] > len(agents) * 2 and self.engine.can_spawn_agent():
            await self._request_new_agent()

    def _compute_avg_completion_rate(self, agents: dict) -> float:
        """Compute average task completion rate across all agents."""
        rates = []
        for agent in agents.values():
            total = agent.performance["tasks_completed"] + agent.performance["tasks_failed"]
            if total > 0:
                rates.append(agent.performance["tasks_completed"] / total)
        return sum(rates) / len(rates) if rates else 1.0

    def _identify_bottlenecks(self, agents: dict) -> list[dict]:
        """Identify communication or task bottlenecks."""
        bottlenecks = []
        for agent_id, agent in agents.items():
            if len(agent.task_queue) > 5:
                bottlenecks.append({
                    "agent_id": agent_id,
                    "type": "task_overload",
                    "queue_length": len(agent.task_queue),
                })
        return bottlenecks

    async def _resolve_bottlenecks(self, bottlenecks: list[dict]):
        """Resolve identified bottlenecks."""
        for bottleneck in bottlenecks:
            agent_id = bottleneck["agent_id"]
            if bottleneck["type"] == "task_overload":
                # Reassign some tasks to idle agents
                agent = self.engine.agents.get(agent_id)
                if agent and len(agent.task_queue) > 3:
                    # Find idle agent
                    for other_id, other in self.engine.agents.items():
                        if other_id != agent_id and len(other.task_queue) == 0:
                            task = agent.task_queue.pop()
                            other.task_queue.append(task)
                            logger.info(f"Reassigned task from {agent_id} to {other_id}")
                            break

    async def _request_new_agent(self):
        """Request a new agent if under the cap."""
        if self.engine.can_spawn_agent():
            # Find the office with most pending tasks
            office_tasks = {}
            for agent in self.engine.agents.values():
                if hasattr(agent, 'office_id'):
                    office_tasks[agent.office_id] = office_tasks.get(agent.office_id, 0) + len(agent.task_queue)

            if office_tasks:
                busiest_office = max(office_tasks, key=office_tasks.get)
                logger.info(f"Requesting new agent for office {busiest_office}")
                # Emit event for hierarchy to handle
                await self.engine.event_bus.emit("request_new_agent", {
                    "office_id": busiest_office,
                    "reason": "high_workload",
                })

    async def _execute_task(self, task: dict):
        """Execute efficiency-related tasks."""
        self.status = "working"
        self.thoughts = "Analyzing company efficiency..."

        if task.get("type") == "fire_agent":
            await self._fire_agent(task["agent_id"])
        elif task.get("type") == "reassign_tasks":
            await self._reassign_tasks(task["from_agent"], task["to_agent"])

    async def _fire_agent(self, agent_id: str):
        """Fire an underperforming agent."""
        if agent_id in self.engine.agents:
            agent = self.engine.agents[agent_id]
            if agent.performance["tasks_failed"] > agent.performance["tasks_completed"] * 2:
                logger.info(f"Firing underperforming agent: {agent_id}")
                await agent.stop()
                del self.engine.agents[agent_id]
                await self.engine.event_bus.emit("agent_fired", {
                    "agent_id": agent_id,
                    "reason": "underperformance",
                })

    async def _reassign_tasks(self, from_agent_id: str, to_agent_id: str):
        """Reassign all tasks from one agent to another."""
        from_agent = self.engine.agents.get(from_agent_id)
        to_agent = self.engine.agents.get(to_agent_id)
        if from_agent and to_agent:
            to_agent.task_queue.extend(from_agent.task_queue)
            from_agent.task_queue.clear()

    async def _process_message(self, message: str, sender_id: str) -> str:
        """Process messages about performance issues."""
        self.thoughts = f"Received efficiency report from {sender_id}"
        return "Acknowledged. Monitoring performance."

    async def _idle_behavior(self):
        """Efficiency idle behavior."""
        self.status = "idle"
        self.thoughts = f"Monitoring {len(self.engine.agents)} agents. Last check: {self.monitoring_interval}s ago."
