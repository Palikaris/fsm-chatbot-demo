import asyncio
from src.database import InMemoryDatabase
from src.broker import InMemoryBroker
from src.fsm import ChatFSM
from src.models import SessionState


async def test_fsm():
    """Test the FSM core functionality."""
    print("=== Testing FSM Core ===\n")

    # Initialize components
    db = InMemoryDatabase()
    broker = InMemoryBroker()
    fsm = ChatFSM(db, broker)

    # Test 1: Create session and send message
    print("Test 1: Sending user message...")
    session = await fsm.handle_user_message(
        user_id="test_user",
        message_content="Hello, AI!",
        session_id=None  # New session
    )
    print(f"✓ Session created: {session.id}")
    print(f"✓ State: {session.state.value}")
    print(f"✓ Messages: {len(session.messages)}")
    assert session.state == SessionState.USER_COMMITTED
    assert len(session.messages) == 1
    print()

    # Test 2: Start AI generation
    print("Test 2: Starting AI generation...")
    session = await fsm.start_ai_generation(session.id)
    print(f"✓ State: {session.state.value}")
    assert session.state == SessionState.AI_GENERATING
    print()

    # Test 3: Commit AI message
    print("Test 3: Committing AI message...")
    session = await fsm.commit_ai_message(session.id, "Hello, human!")
    print(f"✓ State: {session.state.value}")
    print(f"✓ Messages: {len(session.messages)}")
    assert session.state == SessionState.IDLE
    assert len(session.messages) == 2
    print()

    # Test 4: Send another message
    print("Test 4: Sending follow-up message...")
    session = await fsm.handle_user_message(
        user_id="test_user",
        message_content="How are you?",
        session_id=session.id
    )
    print(f"✓ State: {session.state.value}")
    print(f"✓ Messages: {len(session.messages)}")
    assert session.state == SessionState.USER_COMMITTED
    assert len(session.messages) == 3
    print()

    # Test 5: Invalid state transition
    print("Test 5: Testing invalid state transition...")
    try:
        await fsm.handle_user_message(
            user_id="test_user",
            message_content="This should fail",
            session_id=session.id
        )
        print("✗ Should have raised error!")
    except ValueError as e:
        print(f"✓ Correctly rejected: {e}")
    print()

    print("=== All Tests Passed! ===")


if __name__ == "__main__":
    asyncio.run(test_fsm())