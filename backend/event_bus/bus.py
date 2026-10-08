"""
Event Bus - Async message broker for agent communication.
"""
import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """In-process async event bus for agent communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._dispatcher_task: asyncio.Task | None = None

    async def start(self):
        """Start the event bus dispatcher."""
        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
        logger.info("Event bus started")

    async def stop(self):
        """Stop the event bus."""
        self._running = False
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")

    async def emit(self, event_type: str, data: dict):
        """Emit an event to all subscribers."""
        await self._queue.put((event_type, data))

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    async def _dispatch_loop(self):
        """Main dispatch loop."""
        while self._running:
            try:
                event_type, data = await self._queue.get()
                await self._dispatch(event_type, data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Event dispatch error: {e}")

    async def _dispatch(self, event_type: str, data: dict):
        """Dispatch event to all subscribers."""
        callbacks = self._subscribers.get(event_type, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event_type, data))
                else:
                    callback(event_type, data)
            except Exception as e:
                logger.error(f"Subscriber error for {event_type}: {e}")
