# src/interfaces.py
from abc import ABC, abstractmethod
from typing import Optional, List
import asyncio

# Import your models
from src.models import Session, StreamEvent


class IDatabase(ABC):
    """Database abstraction for session storage.
    """

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID."""
        pass

    @abstractmethod
    async def create_session(self, session: Session) -> None:
        """Create a new session."""
        pass

    @abstractmethod
    async def update_session(self, session: Session) -> None:
        """Update an existing session."""
        pass

    @abstractmethod
    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all sessions for a user."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        pass


class IMessageBroker(ABC):
    """Message broker abstraction for async communication.

    Handles queuing sessions for AI processing and streaming events to clients.
    """

    @abstractmethod
    async def enqueue_session(self, session_id: str) -> None:
        """Enqueue a session for AI processing."""
        pass

    @abstractmethod
    async def dequeue_session(self, timeout: float = 1.0) -> Optional[str]:
        """Dequeue the next session to process.

        Args:
            timeout: How long to wait for a session (in seconds)

        Returns:
            Session ID or None if timeout
        """
        pass

    @abstractmethod
    async def send_event(self, session_id: str, event: StreamEvent) -> None:
        """Send an event to a specific session's stream."""
        pass

    @abstractmethod
    async def get_session_events(self, session_id: str) -> asyncio.Queue:
        """Get the event queue for a session.

        Returns an asyncio.Queue that consumers can read from.
        """
        pass

    @abstractmethod
    async def cleanup_session_queue(self, session_id: str) -> None:
        """Clean up a session's event queue when done."""
        pass