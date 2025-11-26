# examples/simple_conversation.py
# !/usr/bin/env python3
"""
Simple conversation example using Python requests.
Demonstrates the full flow: send message -> stream response -> repeat.
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"
USER_ID = "demo_user"


def send_message(user_id: str, message: str, session_id: str = None):
    """Send a message and get session ID."""
    url = f"{BASE_URL}/sessions/{user_id}/messages"
    payload = {
        "user_id": user_id,
        "message": message,
    }
    if session_id:
        payload["session_id"] = session_id

    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()


def stream_response(session_id: str):
    """Stream AI response and print tokens in real-time."""
    url = f"{BASE_URL}/sessions/{session_id}/stream"

    with requests.get(url, stream=True) as response:
        response.raise_for_status()

        current_event = None

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                current_event = None
                continue

            if line.startswith('event:'):
                # Strip whitespace from event type
                current_event = line.split(':', 1)[1].strip()
            elif line.startswith('data:'):
                # DON'T strip the data - preserve leading/trailing spaces!
                data = line.split(':', 1)[1]
                # Only strip the single space that SSE format adds after the colon
                if data.startswith(' '):
                    data = data[1:]  # Remove just the first space after "data: "

                if current_event == 'token':
                    print(data, end='', flush=True)
                elif current_event == 'commit_done':
                    print()
                    return
                elif current_event == 'error':
                    print(f"\n[Error: {data}]")
                    return

def get_session(session_id: str):
    """Get full session details."""
    url = f"{BASE_URL}/sessions/{session_id}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def main():
    print("=" * 60)
    print("FSM CHATBOT DEMO - SIMPLE CONVERSATION")
    print("=" * 60)
    print()

    # First message
    print("User: Hello!")
    result = send_message(USER_ID, "Hello!")
    session_id = result["session_id"]
    print(f"[Session created: {session_id}]")
    print()

    print("AI: ", end='', flush=True)
    stream_response(session_id)
    print()

    # Follow-up message
    print("User: How are you?")
    send_message(USER_ID, "How are you?", session_id=session_id)
    print()

    print("AI: ", end='', flush=True)
    stream_response(session_id)
    print()

    # Show full history
    print("\n" + "=" * 60)
    print("FULL SESSION HISTORY")
    print("=" * 60)
    session_data = get_session(session_id)
    session = session_data["session"]

    for msg in session["messages"]:
        role = msg["role"].capitalize()
        content = msg["content"]
        timestamp = msg["timestamp"]
        print(f"\n{role} [{timestamp}]:")
        print(f"  {content}")

    print(f"\nSession State: {session['state']}")
    print(f"Total Messages: {len(session['messages'])}")
    print(f"Created: {session['created_at']}")
    print(f"Last Updated: {session['updated_at']}")

    print("\n" + "=" * 60)
    print("CONVERSATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n" + "=" * 60, file=sys.stderr)
        print("ERROR: Cannot connect to server", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("\nIs the server running?", file=sys.stderr)
        print("Start with: python -m uvicorn src.main:app --reload", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)