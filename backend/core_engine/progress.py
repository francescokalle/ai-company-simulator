"""
Progress Tracker - Emits real-time progress events during onboarding/analysis.

Every phase update is emitted on the event bus as `analysis_progress`, so the
frontend can show a live progress bar with the current step description.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProgressState:
    """Snapshot of onboarding progress."""
    phase: str = "idle"           # idle, analyzing, building_memory, creating_offices, spawning_agents, complete, error, paused
    step: int = 0                 # current step number
    total_steps: int = 8          # total steps in the pipeline
    percent: float = 0.0          # 0-100
    message: str = ""             # human-readable description of current work
    detail: str = ""              # extra detail (e.g. file being analyzed)
    started_at: float = field(default_factory=time.time)
    elapsed: float = 0.0
    error: Optional[str] = None
    paused: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressTracker:
    """
    Tracks onboarding progress and broadcasts updates.
    Pausable: when paused, wait_if_paused() blocks until resumed.
    """

    # Canonical step list (must match the pipeline in engine.py)
    STEPS = [
        "fetch",           # 1. download/clone the project
        "scan",            # 2. scan source files
        "components",      # 3. identify components
        "relationships",   # 4. extract dependencies
        "memory",          # 5. build vector + graph memory
        "offices",         # 6. create offices and agents
        "leadership",      # 7. spawn CEO + Efficiency
        "finalize",        # 8. persist and finish
    ]

    def __init__(self, emit: Callable[[str, dict], Any]):
        """
        Args:
            emit: async callable(event_type, data) to broadcast progress.
        """
        self._emit = emit
        self.state = ProgressState(total_steps=len(self.STEPS))
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._aborted = False

    # ---------- lifecycle ----------

    def reset(self):
        """Reset progress for a new run."""
        self.state = ProgressState(total_steps=len(self.STEPS))
        self._aborted = False
        self._pause_event.set()

    def abort(self):
        """Signal the pipeline to stop at the next checkpoint."""
        self._aborted = True
        self._pause_event.set()  # unblock so the loop can notice the abort

    @property
    def aborted(self) -> bool:
        return self._aborted

    def pause(self):
        """Pause the pipeline (blocks at the next checkpoint)."""
        self.state.paused = True
        self.state.phase = "paused"
        self._pause_event.clear()

    def resume(self):
        """Resume a paused pipeline."""
        self.state.paused = False
        self._pause_event.set()

    async def wait_if_paused(self):
        """Block while paused. Raises asyncio.CancelledError if aborted."""
        await self._pause_event.wait()
        if self._aborted:
            raise asyncio.CancelledError("Onboarding aborted by user")

    # ---------- progress updates ----------

    async def start_step(self, step_name: str, message: str, detail: str = ""):
        """Begin a named step and broadcast the update."""
        if step_name in self.STEPS:
            self.state.step = self.STEPS.index(step_name) + 1
        self.state.phase = step_name
        self.state.message = message
        self.state.detail = detail
        self.state.error = None
        self.state.elapsed = round(time.time() - self.state.started_at, 1)
        await self._broadcast()

    async def update_detail(self, detail: str):
        """Update the sub-detail of the current step without changing phase."""
        self.state.detail = detail
        self.state.elapsed = round(time.time() - self.state.started_at, 1)
        await self._broadcast()

    async def update_message(self, message: str):
        """Update the main message of the current step."""
        self.state.message = message
        self.state.elapsed = round(time.time() - self.state.started_at, 1)
        await self._broadcast()

    async def complete(self, message: str = "Azienda creata con successo"):
        """Mark the pipeline as complete."""
        self.state.phase = "complete"
        self.state.step = self.state.total_steps
        self.state.percent = 100.0
        self.state.message = message
        self.state.detail = ""
        self.state.paused = False
        self.state.elapsed = round(time.time() - self.state.started_at, 1)
        await self._broadcast()

    async def fail(self, error: str):
        """Mark the pipeline as failed."""
        self.state.phase = "error"
        self.state.error = error
        self.state.message = "Errore durante la creazione"
        self.state.elapsed = round(time.time() - self.state.started_at, 1)
        await self._broadcast()

    async def _broadcast(self):
        """Compute percent and emit the state."""
        if self.state.total_steps > 0:
            base = (self.state.step - 1) / self.state.total_steps
            self.state.percent = round(min(100.0, base * 100), 1)
        payload = self.state.to_dict()
        payload["steps"] = self.STEPS
        try:
            await self._emit("analysis_progress", payload)
        except Exception as e:
            logger.error(f"Progress broadcast failed: {e}")

    def get_state(self) -> dict:
        """Return the current state as a dict (for REST polling)."""
        return self.state.to_dict()
