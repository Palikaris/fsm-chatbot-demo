# src/database.py
from typing import Optional, List, Dict
import asyncio

from src.interfaces import IDatabase
from src.models import Session


class InMemoryDatabase(IDatabase):
    """Simple in-memory database using a dict.
    Note: Not thread-safe for production, but fine for demo.
    """

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        # In Python, we need a lock for async thread safety
        self._lock = asyncio.Lock()

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def create_session(self, session: Session) -> None:
        """Create a new session."""
        async with self._lock:
            if session.id in self._sessions:
                raise ValueError(f"Session {session.id} already exists")
            self._sessions[session.id] = session

    async def update_session(self, session: Session) -> None:
        """Update an existing session."""
        async with self._lock:
            if session.id not in self._sessions:
                raise ValueError(f"Session {session.id} not found")
            self._sessions[session.id] = session

    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all sessions for a user."""
        async with self._lock:
            # List comprehension - like C# LINQ: sessions.Where(s => s.UserId == userId).ToList()
            return [s for s in self._sessions.values() if s.user_id == user_id]

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]