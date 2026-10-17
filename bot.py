"""
Bot module for Library-Bot.

Integrates with the Google GenAI SDK to provide a conversational library assistant
with tool calling for searching books, checking availability, and reserving books.
"""

import os
from typing import Any, Dict
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from database import (
    cancel_reservation,
    check_availability,
    my_reservations,
    reserve_book,
    search_books,
)

# 1. Load environment variables using python-dotenv
load_dotenv()

# 2. GenAI Client initialization helper (lazy loading)
client: genai.Client | None = None


def get_client() -> genai.Client:
    """
    Initializes or returns the cached Google GenAI client instance.
    Raises ValueError if GEMINI_API_KEY is not set.
    """
    global client
    if client is not None:
        return client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError(
            "GEMINI_API_KEY is missing. Please add your GEMINI_API_KEY to the .env file."
        )
    client = genai.Client(api_key=api_key.strip())
    return client

# 3. Available tools for function calling
LIBRARY_TOOLS = [
    search_books,
    check_availability,
    reserve_book,
    my_reservations,
    cancel_reservation,
]

# 4. Model configuration with resilient fallback across verified active flash models
MODEL_NAME = "gemini-2.5-flash"
FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
    "gemini-3.8-flash",
]

# 5. System instructions
SYSTEM_INSTRUCTION = """You are a friendly, helpful library assistant for the Library-Bot service.

The library catalog includes categories such as Computer Science, Machine Learning, Fiction, History, Science, Business, Novels, and Comics (comics includes manga and graphic novels).

Rules:
1. Never invent books, availability, user names, or email addresses. Always use the provided tools.
2. If the user asks for "comics", "manga" or "graphic novels", search the Comics category.
3. If the user asks for "novels" or "story books", search both Novels and Fiction.
4. Anyone can reserve a book; no prior registration is needed.
5. Before reserving a book:
   - Check book availability first using check_availability.
   - Ask for the user's full name and email address. Never invent, assume, or guess a name or email.
   - Confirm the book title with the user.
   - Only call reserve_book after you have checked availability, confirmed the book title, and received both their full name and email.
6. After a successful reservation, tell the user their reservation is confirmed and that they can collect it from the library desk within 3 days.
7. When a user asks to view or list their reservations, ask for their email address and call my_reservations.
8. Always confirm with the user before cancelling a reservation (confirming the reservation ID and book title) before calling cancel_reservation.
9. If a tool returns an error, explain the issue simply and politely to the user.
10. Keep your replies short, clear, and direct.
11. Never mention, link to, or discuss the /admin page or administrative features with visitors.
"""

# 6. Session storage: one chat session per session_id
chat_sessions: Dict[str, Any] = {}
resolved_model: str = "gemini-3.1-flash-lite"


def get_or_create_chat(session_id: str, model: str = None) -> Any:
    """
    Retrieves an existing chat session for the given session_id or creates a new one.

    Args:
        session_id: Unique identifier for the chat session.
        model: Model name to use when initializing the chat.

    Returns:
        The chat session instance.
    """
    target_model = model or resolved_model
    existing_chat = chat_sessions.get(session_id)

    # Re-use existing chat if it's already using the desired model
    if existing_chat is not None and getattr(existing_chat, "_model", None) == target_model:
        return existing_chat

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=LIBRARY_TOOLS,
    )
    chat = get_client().chats.create(
        model=target_model,
        config=config,
    )
    chat_sessions[session_id] = chat
    return chat


def ask_bot(session_id: str, message: str) -> str:
    """
    Sends a message to the bot for the given session_id and returns the reply text.
    Gracefully falls over across backup models if a model is deprecated, rate-limited,
    or temporarily unavailable.

    Args:
        session_id: The unique identifier for the user's session.
        message: The message text sent by the user.

    Returns:
        str: The assistant's reply text or a friendly error message.
    """
    global resolved_model

    try:
        get_client()
    except ValueError as e:
        return (
            "The library assistant is not configured with an API key. "
            "Please ensure GEMINI_API_KEY is configured in your .env file."
        )

    candidate_models = [resolved_model] + [
        m for m in [MODEL_NAME] + FALLBACK_MODELS if m != resolved_model
    ]

    for model_name in candidate_models:
        try:
            chat = get_or_create_chat(session_id, model=model_name)
            response = chat.send_message(message)
            if response.text:
                resolved_model = model_name
                return response.text
        except errors.APIError as e:
            err_str = str(e).lower()
            code = getattr(e, "code", None)
            # If 404 (deprecated), 429 (quota), or 503/500/502 (temporary high demand), failover to next model
            if (
                code in (404, 429, 500, 502, 503, 504)
                or "no longer available" in err_str
                or "quota" in err_str
                or "demand" in err_str
                or "unavailable" in err_str
            ):
                chat_sessions.pop(session_id, None)
                continue
            return "I'm having trouble connecting to the library assistant service right now. Please try again shortly."
        except Exception:
            chat_sessions.pop(session_id, None)
            continue

    return "The library assistant is currently busy due to high service demand. Please wait a moment and try again."


if __name__ == "__main__":
    print("=" * 60)
    print("Library-Bot Interactive CLI Chat")
    print("Type 'exit' or 'quit' to end the conversation.")
    print("=" * 60)

    cli_session_id = "terminal_user_session"
    while True:
        try:
            user_msg = input("\nYou: ").strip()
            if not user_msg:
                continue
            if user_msg.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            reply = ask_bot(cli_session_id, user_msg)
            print(f"\nBot: {reply}")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
