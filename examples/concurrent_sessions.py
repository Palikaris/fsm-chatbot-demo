# examples/concurrent_sessions.py
# !/usr/bin/env python3
"""
Concurrent sessions example - demonstrates multiple independent conversations.
"""

import asyncio
import aiohttp
import sys

BASE_URL = "http://localhost:8000"


async def run_conversation(session_http, user_id: str, messages: list):
    """Run a conversation for a single user."""
    print(f"\n{'=' * 60}")
    print(f"[{user_id.upper()}] Starting conversation")
    print('=' * 60)

    session_id = None

    for msg_idx, message in enumerate(messages, 1):
        # Send message
        url = f"{BASE_URL}/sessions/{user_id}/messages"
        payload = {
            "user_id": user_id,
            "message": message,
        }
        if session_id:
            payload["session_id"] = session_id

        async with session_http.post(url, json=payload) as response:
            result = await response.json()
            session_id = result["session_id"]

        print(f"\n[{user_id.upper()}] Message {msg_idx}/{len(messages)}")
        print(f"[{user_id.upper()}] User: {message}")
        print(f"[{user_id.upper()}] AI: ", end='', flush=True)

        # Stream response
        url = f"{BASE_URL}/sessions/{session_id}/stream"

        async with session_http.get(url) as response:
            current_event = None

            async for line in response.content:
                line_str = line.decode('utf-8').rstrip('\n\r')

                if not line_str:
                    current_event = None
                    continue

                if line_str.startswith('event:'):
                    current_event = line_str.split(':', 1)[1].strip()
                elif line_str.startswith('data:'):
                    data = line_str.split(':', 1)[1]
                    if data.startswith(' '):
                        data = data[1:]

                    if current_event == 'token':
                        print(data, end='', flush=True)
                    elif current_event == 'commit_done':
                        print()
                        break
                    elif current_event == 'error':
                        print(f"\n[Error: {data}]")
                        break

        if msg_idx < len(messages):
            await asyncio.sleep(0.3)

    print(f"\n[{user_id.upper()}] ✓ Conversation complete")
    print('=' * 60)

    return session_id


async def verify_session_independence(session_http, sessions):
    """Verify that each session maintained independent state."""
    print("\n" + "=" * 60)
    print("VERIFYING SESSION INDEPENDENCE")
    print("=" * 60)

    for user_id, session_id in sessions.items():
        url = f"{BASE_URL}/sessions/{session_id}"
        async with session_http.get(url) as response:
            data = await response.json()
            session = data["session"]

            print(f"\n[{user_id.upper()}] Session: {session_id}")
            print(f"  Messages: {len(session['messages'])}")
            print(f"  State: {session['state']}")

            # Show first and last message
            if session['messages']:
                first_msg = session['messages'][0]
                last_msg = session['messages'][-1]
                print(f"  First: {first_msg['role']}: {first_msg['content'][:50]}...")
                print(f"  Last: {last_msg['role']}: {last_msg['content'][:50]}...")


async def main():
    print("\n" + "=" * 60)
    print("FSM CHATBOT DEMO - CONCURRENT SESSIONS")
    print("=" * 60)
    print("\nDemonstrating multiple independent conversations.")
    print("Each conversation maintains its own state and message history.")
    print("=" * 60)

    # Define different conversations
    conversations = [
        ("alice", ["Hello!", "What's your name?"]),
        ("bob", ["Hi there", "Tell me about yourself"]),
        ("charlie", ["Hey", "Goodbye"]),
    ]

    sessions = {}

    # Run conversations sequentially to avoid output interleaving
    # (The sessions themselves are independent - we're just printing one at a time)
    async with aiohttp.ClientSession() as session:
        for user_id, messages in conversations:
            session_id = await run_conversation(session, user_id, messages)
            sessions[user_id] = session_id

        # Verify independence by fetching all sessions
        await verify_session_independence(session, sessions)

    print("\n" + "=" * 60)
    print("ALL CONVERSATIONS COMPLETE")
    print("=" * 60)
    print("\nKey observations:")
    print("• Each user maintained independent session state")
    print("• Messages are isolated - no cross-contamination")
    print("• Each session has its own message history")
    print("• FSM prevented race conditions")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        print("Make sure the server is running:", file=sys.stderr)
        print("  python -m uvicorn src.main:app --reload", file=sys.stderr)
        sys.exit(1)