# src/fsm.py
from typing import Optional
import uuid
from datetime import datetime

from src.interfaces import IDatabase, IMessageBroker
from src.models import Session, SessionState, Message


class ChatFSM:
    """Finite State Machine for chat session coordination.

    Production Considerations that should be implemented:
    - Timeout detection: Use session.updated_at to find stuck sessions
    - Recovery: Background job to transition TIMEOUT states back to IDLE
    - Alerting: Monitor sessions stuck in GENERATING for >30s
    - Cleanup: Archive or delete sessions in TIMEOUT after 24h
    """

    def __init__(self, database: IDatabase, broker: IMessageBroker):
        self.db = database
        self.broker = broker

    async def handle_user_message(
            self,
            user_id: str,
            message_content: str,
            session_id: Optional[str] = None
    ) -> Session:
        """Handle incoming user message.

        Flow:
        1. Get or create session
        2. Validate state (must be IDLE or AI_COMMITTED)
        3. Transition to USER_WRITING (optimistic)
        4. Add message to session
        5. Transition to USER_COMMITTED (sync)
        6. Enqueue for AI processing
        7. Return updated session
        """

        # Get or create session
        if session_id:
            session = await self.db.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            if session.user_id != user_id:
                raise ValueError(f"Session {session_id} does not belong to user {user_id}")
        else:
            # Create new session
            session = Session(
                id=str(uuid.uuid4()),
                user_id=user_id,
                state=SessionState.IDLE,
            )
            await self.db.create_session(session)

        # Validate state - can only accept messages when IDLE or AI_COMMITTED
        if session.state not in [SessionState.IDLE, SessionState.AI_COMMITTED]:
            raise ValueError(
                f"Cannot accept message in state {session.state.value}. "
                f"Session must be IDLE or AI_COMMITTED."
            )

        try:
            # State 1: USER_WRITING (optimistic update)
            session.update_state(SessionState.USER_WRITING)
            await self.db.update_session(session)

            # Add user message
            user_msg = Message(
                id=str(uuid.uuid4()),
                role="user",
                content=message_content,
                timestamp=datetime.utcnow(),
            )
            session.add_message(user_msg)

            # State 2: USER_COMMITTED (sync commit)
            session.update_state(SessionState.USER_COMMITTED)
            await self.db.update_session(session)

            # Enqueue for AI processing
            await self.broker.enqueue_session(session.id)

            return session

        except Exception as e:
            # On error, transition to ERROR state
            session.update_state(SessionState.ERROR, error_msg=str(e))
            await self.db.update_session(session)
            raise

    async def start_ai_generation(self, session_id: str) -> Session:
        """Mark session as AI_GENERATING.

        Called by AI service when it picks up work.
        """
        session = await self.db.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Validate state
        if session.state != SessionState.USER_COMMITTED:
            raise ValueError(
                f"Cannot start AI generation in state {session.state.value}. "
                f"Expected USER_COMMITTED."
            )

        session.update_state(SessionState.AI_GENERATING)
        await self.db.update_session(session)
        return session

    async def commit_ai_message(self, session_id: str, message_content: str) -> Session:
        """Commit AI message and transition to AI_COMMITTED.

        Called by AI service after streaming is complete.
        """
        session = await self.db.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Validate state
        if session.state != SessionState.AI_GENERATING:
            raise ValueError(
                f"Cannot commit AI message in state {session.state.value}. "
                f"Expected AI_GENERATING."
            )

        # Add AI message
        ai_msg = Message(
            id=str(uuid.uuid4()),
            role="assistant",
            content=message_content,
            timestamp=datetime.utcnow(),
        )
        session.add_message(ai_msg)

        # Transition to AI_COMMITTED, then back to IDLE
        session.update_state(SessionState.AI_COMMITTED)
        await self.db.update_session(session)

        # Immediately transition back to IDLE (ready for next message)
        session.update_state(SessionState.IDLE)
        await self.db.update_session(session)

        return session

    async def mark_error(self, session_id: str, error_message: str) -> Session:
        """Mark session as ERROR state.

        Can be called from any state if something goes wrong.
        """
        session = await self.db.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.update_state(SessionState.ERROR, error_msg=error_message)
        session.retry_count += 1
        await self.db.update_session(session)
        return session