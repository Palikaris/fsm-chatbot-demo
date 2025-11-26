# src/ai_service.py
import asyncio
from typing import Optional
import logging

from src.interfaces import IDatabase, IMessageBroker
from src.fsm import ChatFSM
from src.models import StreamEvent

# Set up logging so we can see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIService:
    """Background service that processes sessions and generates AI responses.

    In production, this would:
    - Call actual LLM API (OpenAI, Anthropic, etc.)
    - Handle rate limiting and retries
    - Potentially run on separate workers/pods

    For demo:
    - Generate mock tokens word-by-word
    - Simulate streaming delay
    - Show the pattern
    """

    def __init__(self, fsm: ChatFSM, broker: IMessageBroker):
        self.fsm = fsm
        self.broker = broker
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background processing loop."""
        if self._running:
            logger.warning("AI Service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("AI Service started")

    async def stop(self):
        """Stop the background processing loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AI Service stopped")

    async def _process_loop(self):
        """Main processing loop - dequeues sessions and generates responses.
        """
        logger.info("AI Service processing loop started")

        while self._running:
            try:
                # Dequeue next session (with timeout)
                session_id = await self.broker.dequeue_session(timeout=1.0)

                if session_id:
                    logger.info(f"Processing session: {session_id}")
                    await self._process_session(session_id)
                else:
                    # No work available, sleep a bit
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Back off on error

    async def _process_session(self, session_id: str):
        """Process a single session - generate and stream AI response.

        Flow:
        1. Transition to AI_GENERATING
        2. Get the last user message
        3. Generate response (mock)
        4. Stream tokens via broker
        5. Commit final message
        6. Send completion event
        """
        try:
            # Step 1: Transition to AI_GENERATING
            session = await self.fsm.start_ai_generation(session_id)
            logger.info(f"Session {session_id} state: {session.state.value}")

            # Step 2: Get last user message
            last_message = session.messages[-1] if session.messages else None
            if not last_message or last_message.role != "user":
                raise ValueError("No user message found")

            # Step 3: Generate mock response
            response = self._generate_mock_response(last_message.content)

            # Step 4: Stream tokens
            logger.info(f"Streaming {len(response.split())} tokens for session {session_id}")
            await self._stream_response(session_id, response)

            # Step 5: Commit final message
            await self.fsm.commit_ai_message(session_id, response)
            logger.info(f"Session {session_id} completed")

            # Step 6: Send completion event
            completion_event = StreamEvent(
                event_type="commit_done",
                data=session_id
            )
            await self.broker.send_event(session_id, completion_event)

        except Exception as e:
            logger.error(f"Error processing session {session_id}: {e}", exc_info=True)
            # Mark session as errored
            try:
                await self.fsm.mark_error(session_id, str(e))
                # Send error event to client
                error_event = StreamEvent(
                    event_type="error",
                    data=str(e)
                )
                await self.broker.send_event(session_id, error_event)
            except Exception as mark_error_ex:
                logger.error(f"Failed to mark error: {mark_error_ex}", exc_info=True)

    def _generate_mock_response(self, user_message: str) -> str:
        """Generate a mock AI response.

        In production: An actual LLM API would be called here.
        For demo: Simple rule-based responses are A-OK.
        """
        user_lower = user_message.lower()

        if "hello" in user_lower or "hi" in user_lower:
            return "Hello! I'm a mock AI assistant. How can I help you today?"
        elif "how are you" in user_lower:
            return "I'm doing well, thank you for asking! I'm a demo chatbot showcasing FSM-based state management."
        elif "bye" in user_lower or "goodbye" in user_lower:
            return "Goodbye! Thanks for chatting with me. Feel free to start a new conversation anytime."
        elif "name" in user_lower:
            return "I'm FSM Bot, a demonstration chatbot built to showcase distributed systems patterns."
        else:
            return f"I received your message: '{user_message}'. This is a mock response demonstrating token streaming and state management."

    async def _stream_response(self, session_id: str, response: str):
        """Stream response word-by-word to simulate real LLM streaming.
        """
        words = response.split()

        for i, word in enumerate(words):
            # For first word, no leading space. For subsequent words, add space.
            if i == 0:
                token = word
            else:
                token = f" {word}"  # Space comes BEFORE the word

            # Send token event
            event = StreamEvent(
                event_type="token",
                data=token
            )
            await self.broker.send_event(session_id, event)

            # Simulate streaming delay (50ms per token)
            await asyncio.sleep(0.05)

        # Send message_end event
        end_event = StreamEvent(
            event_type="message_end",
            data=""
        )
        await self.broker.send_event(session_id, end_event)
