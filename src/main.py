# src/main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import logging

from src.database import InMemoryDatabase
from src.broker import InMemoryBroker
from src.fsm import ChatFSM
from src.ai_service import AIService
from src.models import Session

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="FSM Chatbot Demo",
    description="Production-pattern demonstration of FSM-based chat coordination",
    version="1.0.0"
)

# Initialize components (singleton pattern)
database = InMemoryDatabase()
broker = InMemoryBroker()
fsm = ChatFSM(database, broker)
ai_service = AIService(fsm, broker)


# Pydantic models for request/response validation
class SendMessageRequest(BaseModel):
    """Request body for sending a message."""
    user_id: str
    message: str
    session_id: Optional[str] = None


class SendMessageResponse(BaseModel):
    """Response after sending a message."""
    session_id: str
    status: str
    message: str


class SessionResponse(BaseModel):
    """Response containing full session details."""
    session: dict


# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    """Start background AI service when app starts."""
    await ai_service.start()
    logger.info("FastAPI application started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background AI service when app shuts down."""
    await ai_service.stop()
    logger.info("FastAPI application stopped")


# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "FSM Chatbot Demo",
        "version": "1.0.0"
    }


@app.post("/sessions/{user_id}/messages", response_model=SendMessageResponse)
async def send_message(user_id: str, request: SendMessageRequest):
    """Send a message to the chatbot.

    This endpoint:
    1. Validates the request
    2. Calls FSM to handle the message
    3. Returns session ID for streaming

    The actual AI response will be streamed via /sessions/{session_id}/stream
    """
    try:
        # Override user_id from path (more RESTful)
        session = await fsm.handle_user_message(
            user_id=user_id,
            message_content=request.message,
            session_id=request.session_id
        )

        return SendMessageResponse(
            session_id=session.id,
            status="ok",
            message="Message received. Connect to /sessions/{session_id}/stream for response."
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/sessions/{session_id}/stream")
async def stream_response(session_id: str):
    """Stream AI response via Server-Sent Events (SSE).

    This endpoint:
    1. Opens an SSE connection
    2. Streams tokens as they're generated
    3. Sends completion event when done
    4. Cleans up resources

    SSE format:
    event: token
    data: Hello

    event: token
    data:  world

    event: message_end
    data:

    event: commit_done
    data: <session_id>
    """

    # Verify session exists
    session = await database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        """Generator that yields SSE events.

        This is the heart of the streaming - we pull events from the broker
        and yield them in SSE format.
        """
        try:
            # Get the event queue for this session
            event_queue = await broker.get_session_events(session_id)
            logger.info(f"SSE connection opened for session {session_id}")

            while True:
                try:
                    # Wait for next event (with timeout to allow checking if done)
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)

                    # Yield event in SSE format
                    yield event.to_sse_format()

                    # If this is the final event, break
                    if event.event_type in ["commit_done", "error"]:
                        logger.info(f"SSE connection closing for session {session_id}: {event.event_type}")
                        break

                except asyncio.TimeoutError:
                    # Send keepalive comment (SSE supports comments with :)
                    yield ": keepalive\n\n"
                    continue

        except Exception as e:
            logger.error(f"Error in SSE stream: {e}", exc_info=True)
            # Send error event
            error_event = f"event: error\ndata: {str(e)}\n\n"
            yield error_event
        finally:
            # Cleanup
            await broker.cleanup_session_queue(session_id)
            logger.info(f"SSE cleanup complete for session {session_id}")

    # Return streaming response with SSE headers
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get full session details including message history."""
    session = await database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(session=session.to_dict())


@app.get("/sessions/user/{user_id}")
async def get_user_sessions(user_id: str):
    """Get all sessions for a user."""
    sessions = await database.get_user_sessions(user_id)
    return {
        "user_id": user_id,
        "sessions": [s.to_dict() for s in sessions]
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    session = await database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await database.delete_session(session_id)
    return {"status": "ok", "message": f"Session {session_id} deleted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)