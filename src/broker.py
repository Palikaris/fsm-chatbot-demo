# src/broker.py
from typing import Optional, Dict
import asyncio
from queue import Queue, Empty

from src.interfaces import IMessageBroker
from src.models import StreamEvent


class InMemoryBroker(IMessageBroker):
    """Simple in-memory message broker using queues.
    Note: Using thread-safe queue.Queue for work queue,
    asyncio.Queue for session-specific event queues.
    """

    def __init__(self):
        # Work queue: sessions waiting for AI processing
        # Using thread-safe Queue (not asyncio.Queue) because we'll access from multiple contexts
        self._work_queue: Queue[str] = Queue()

        # Session-specific event queues for SSE streaming
        # Key: session_id, Value: asyncio.Queue of StreamEvents
        self._session_queues: Dict[str, asyncio.Queue] = {}

        self._lock = asyncio.Lock()

    async def enqueue_session(self, session_id: str) -> None:
        """Enqueue a session for AI processing."""
        self._work_queue.put(session_id)

    async def dequeue_session(self, timeout: float = 1.0) -> Optional[str]:
        """Dequeue the next session to process.
        This is a blocking operation with timeout.
        """
        try:
            # get_nowait() is non-blocking - like TryDequeue
            # But we want to wait a bit, so we'll use asyncio.sleep in a loop
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                try:
                    return self._work_queue.get_nowait()
                except Empty:
                    await asyncio.sleep(0.1)  # Sleep 100ms and retry
            return None
        except Exception:
            return None

    async def send_event(self, session_id: str, event: StreamEvent) -> None:
        """Send an event to a specific session's stream."""
        async with self._lock:
            # Create queue if it doesn't exist
            if session_id not in self._session_queues:
                self._session_queues[session_id] = asyncio.Queue()

            # Put event in session's queue
            await self._session_queues[session_id].put(event)

    async def get_session_events(self, session_id: str) -> asyncio.Queue:
        """Get the event queue for a session."""
        async with self._lock:
            if session_id not in self._session_queues:
                self._session_queues[session_id] = asyncio.Queue()
            return self._session_queues[session_id]

    async def cleanup_session_queue(self, session_id: str) -> None:
        """Clean up a session's event queue when done."""
        async with self._lock:
            if session_id in self._session_queues:
                del self._session_queues[session_id]