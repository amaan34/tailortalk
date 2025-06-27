import streamlit as st
import httpx
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

# --- Page and Session Configuration ---
st.set_page_config(
    page_title="TailorTalk - AI Booking Assistant",
    page_icon="📅",
    layout="wide"
)

# --- Session State Initialization ---
def initialize_session_state():
    """Initializes all necessary keys in Streamlit's session state."""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'api_base_url' not in st.session_state:
        st.session_state.api_base_url = "http://127.0.0.1:8000"
    # [MODIFICATION] Key to hold an action triggered by a button
    if 'pending_action' not in st.session_state:
        st.session_state.pending_action = None

initialize_session_state()

# --- Backend Communication ---
async def send_message_to_backend(message_content: str) -> None:
    """Sends a user's message to the backend and updates the chat history."""
    if not message_content.strip():
        return

    st.session_state.messages.append({
        "content": message_content, "sender": "user", "timestamp": datetime.now()
    })
    
    with st.chat_message("agent", avatar="🤖"):
        with st.spinner("Thinking..."):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(
                        f"{st.session_state.api_base_url}/chat",
                        json={
                            "content": message_content,
                            "session_id": st.session_state.session_id,
                            "context": {},
                            "sender": "user",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    response.raise_for_status()
                    agent_response = response.json()
                    st.session_state.messages.append({
                        "content": agent_response.get("content", "I don't have a response."),
                        "sender": "agent",
                        "timestamp": datetime.now(),
                        "context": agent_response.get("context", {})
                    })

            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
                st.error(f"Error connecting to backend: {e}")
                st.session_state.messages.append({"content": "Sorry, I'm having trouble connecting to my services.", "sender": "agent"})

# [MODIFICATION] This function now sets a pending action instead of calling the backend directly
def handle_slot_booking(slot: Dict[str, Any]):
    """Sets the booking confirmation message as a pending action in session state."""
    start_time_obj = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
    booking_message = f"I'd like to book the {start_time_obj.strftime('%I:%M %p on %A, %B %d')} slot."
    st.session_state.pending_action = booking_message

# --- UI Display Functions ---
def display_chat_history():
    """Displays all messages and action buttons."""
    for i, msg in enumerate(st.session_state.messages):
        avatar = "🧑" if msg["sender"] == "user" else "🤖"
        with st.chat_message(name=msg["sender"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["sender"] == "agent" and "availability" in msg.get("context", {}):
                display_availability_buttons(msg["context"]["availability"], message_index=i)

def display_availability_buttons(slots: List[Dict], message_index: int):
    """Renders buttons for available time slots."""
    if not slots:
        return
    
    st.markdown("##### ✨ Here are some available slots:")
    cols = st.columns(min(len(slots), 4))
    for i, slot in enumerate(slots[:8]):
        with cols[i % 4]:
            start_time = datetime.fromisoformat(slot["start"].replace('Z', '+00:00'))
            button_text = f"🕒 {start_time.strftime('%I:%M %p')}\n_{start_time.strftime('%a, %b %d')}_"
            button_key = f"slot_{message_index}_{i}"
            
            # [MODIFICATION] Use on_click to call the new handler function
            st.button(
                button_text, 
                key=button_key, 
                help="Click to book this time slot",
                on_click=handle_slot_booking,
                args=(slot,)
            )

# --- Main Application Layout ---
def main():
    st.title("🤖 TailorTalk - Your AI Booking Assistant")
    st.markdown("_An intelligent conversational agent to schedule your appointments._")

    with st.sidebar:
        st.title("⚙️ Configuration")
        api_url = st.text_input("Backend API URL", value=st.session_state.api_base_url)
        st.session_state.api_base_url = api_url
        st.subheader("Session Management")
        st.text(f"Session ID: {st.session_state.session_id[:8]}...")
        if st.button("🔄 Start New Conversation"):
            st.session_state.clear()
            initialize_session_state()
            st.rerun()

    # [MODIFICATION] Handle pending actions at the top of the script run
    if st.session_state.pending_action:
        action = st.session_state.pending_action
        st.session_state.pending_action = None  # Clear the action
        asyncio.run(send_message_to_backend(action))
        st.rerun() # Rerun to display the new messages

    if not st.session_state.messages:
        st.session_state.messages.append({
            "content": "👋 Hello! I'm TailorTalk. How can I help you schedule today?",
            "sender": "agent", "timestamp": datetime.now()
        })

    display_chat_history()

    if user_input := st.chat_input("What can I help you with?"):
        asyncio.run(send_message_to_backend(user_input))
        st.rerun()

if __name__ == "__main__":
    main()