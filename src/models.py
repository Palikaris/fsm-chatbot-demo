# src/models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class SessionState(Enum):
    """Possible states for a chat session.
    """
    IDLE = "idle"
    USER_WRITING = "user_writing"
    USER_COMMITTED = "user_committed"
    AI_GENERATING = "ai_generating"
    AI_COMMITTED = "ai_committed"
    ERROR = "error"
    TIMEOUT = "timeout"


# Valid state transitions
VALID_TRANSITIONS = {
    SessionState.IDLE: [SessionState.USER_WRITING, SessionState.TIMEOUT],
    SessionState.USER_WRITING: [SessionState.USER_COMMITTED, SessionState.ERROR],
    SessionState.USER_COMMITTED: [SessionState.AI_GENERATING, SessionState.ERROR],
    SessionState.AI_GENERATING: [SessionState.AI_COMMITTED, SessionState.ERROR],
    SessionState.AI_COMMITTED: [SessionState.IDLE],
    SessionState.ERROR: [SessionState.IDLE],
    SessionState.TIMEOUT: [SessionState.IDLE],
}


@dataclass
class Message:
    """A single message in a conversation.
    """
    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime

    def to_dict(self) -> dict:
        """Serialize to dict for JSON responses."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Session:
    """A chat session with full state.

    Note: field(default_factory=list) is needed for mutable defaults
    """
    id: str
    user_id: str
    state: SessionState
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    retry_count: int = 0

    def add_message(self, message: Message) -> None:
        """Add a message and update timestamp."""
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

    def update_state(self, new_state: SessionState, error_msg: Optional[str] = None) -> None:
        """Update state and timestamp.

        Validates state transition before applying.
        """
        # Validate transition
        valid_next_states = VALID_TRANSITIONS.get(self.state, [])
        if new_state not in valid_next_states:
            raise ValueError(
                f"Invalid state transition: {self.state.value} -> {new_state.value}. "
                f"Valid transitions: {[s.value for s in valid_next_states]}"
            )

        self.state = new_state
        self.updated_at = datetime.utcnow()

        if error_msg:
            self.error_message = error_msg
        elif new_state != SessionState.ERROR:
            # Clear error message when transitioning away from error
            self.error_message = None

    def to_dict(self) -> dict:
        """Serialize to dict for JSON responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "state": self.state.value,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }


@dataclass
class StreamEvent:
    """An event sent via SSE.

    SSE format requires specific formatting: event: <type>\ndata: <data>\n\n
    """
    event_type: str  # "token", "message_end", "commit_done", "error"
    data: str

    def to_sse_format(self) -> str:
        """Format as SSE event.

        Important: Must end with double newline!
        """
        return f"event: {self.event_type}\ndata: {self.data}\n\n"