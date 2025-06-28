import streamlit as st
import httpx
import uuid
import asyncio
from datetime import datetime
from dateutil import parser
from typing import List, Dict, Any
from streamlit_calendar import calendar  # <-- The import that fixes the NameError

# --- Page and Session Configuration ---
st.set_page_config(
    page_title="TailorTalk - AI Booking Assistant",
    page_icon="📅",
    layout="wide"
)

# --- Session State Initialization ---
def initialize_session_state():
    """Initializes all necessary keys in Streamlit's session state."""
    # This block handles the user's login session ID
    if 'user_session_id' not in st.session_state:
        query_params = st.query_params
        if "session_id" in query_params:
            st.session_state.user_session_id = query_params["session_id"]
            # Important: Clear query params after reading them
            st.query_params.clear()
        else:
            st.session_state.user_session_id = None
    
    # This is a separate ID just for the chat conversation history
    if 'chat_session_id' not in st.session_state:
        st.session_state.chat_session_id = str(uuid.uuid4())

    if 'messages' not in st.session_state:
        st.session_state.messages = []

    if 'api_base_url' not in st.session_state:
        try:
            st.session_state.api_base_url = st.secrets["API_BASE_URL"]
        except (FileNotFoundError, KeyError):
            st.session_state.api_base_url = "http://127.0.0.1:8000"

    if 'upcoming_events' not in st.session_state:
        st.session_state.upcoming_events = []

# --- Backend Communication ---

async def send_message_to_backend(message_content: str):
    """Sends a user's message to the backend and updates the chat history."""
    if not message_content.strip() or not st.session_state.user_session_id:
        return

    st.session_state.messages.append({"content": message_content, "sender": "user"})
    headers = {"X-Session-Id": st.session_state.user_session_id}
    
    with st.chat_message("agent", avatar="🤖"):
        with st.spinner("Thinking..."):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(
                        f"{st.session_state.api_base_url}/chat",
                        json={
                            "content": message_content,
                            "session_id": st.session_state.chat_session_id,
                            "context": {},
                        },
                        headers=headers
                    )
                    response.raise_for_status()
                    agent_response = response.json()
                    st.session_state.messages.append({
                        "content": agent_response.get("content", "I don't have a response."),
                        "sender": "agent", "context": agent_response.get("context", {})
                    })
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                st.error(f"Error connecting to backend: {e}")
                st.session_state.messages.append({"content": "Sorry, I'm having trouble connecting.", "sender": "agent"})

async def fetch_upcoming_events():
    """Fetches events from the backend for the logged-in user."""
    if not st.session_state.user_session_id:
        st.session_state.upcoming_events = []
        return
    
    try:
        headers = {"X-Session-Id": st.session_state.user_session_id}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{st.session_state.api_base_url}/events", headers=headers)
            response.raise_for_status()
            st.session_state.upcoming_events = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        st.sidebar.error("Could not fetch calendar events.")
        st.session_state.upcoming_events = []

# --- UI Display Functions ---

def display_chat_history():
    for msg in st.session_state.messages:
        avatar = "🧑" if msg["sender"] == "user" else "🤖"
        with st.chat_message(name=msg["sender"], avatar=avatar):
            st.markdown(msg["content"])

def display_upcoming_events():
    st.sidebar.subheader("🗓️ Upcoming Events")
    if st.sidebar.button("🔄 Refresh Events"):
        asyncio.run(fetch_upcoming_events())
        st.rerun()

    if not st.session_state.upcoming_events:
        st.sidebar.info("No upcoming events found in your calendar.")
        return

    for event in st.session_state.upcoming_events[:7]:
        summary = event.get('summary', 'No Title')
        start_time_str = event.get('start', {}).get('dateTime')
        if start_time_str:
            start_time = parser.isoparse(start_time_str).strftime('%a, %b %d, %I:%M %p')
            st.sidebar.markdown(f"- **{summary}** at {start_time}")
        else:
            st.sidebar.markdown(f"- **{summary}** (All-day event)")

def display_calendar_view():
    st.subheader("My Calendar View")
    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay",
        },
        "initialView": "dayGridMonth",
    }
    calendar_events = [{
        "title": event.get("summary", "No Title"),
        "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date")),
        "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date")),
        "allDay": "date" in event.get("start", {})
    } for event in st.session_state.upcoming_events]
    
    calendar(events=calendar_events, options=calendar_options)

# --- Main Application Logic ---
def main():
    """Defines the main UI and logic of the Streamlit app."""
    initialize_session_state()
    st.title("🤖 TailorTalk - Your AI Booking Assistant")

    if not st.session_state.user_session_id:
        st.warning("Please connect your Google Calendar to use the assistant.")
        login_url = f"{st.session_state.api_base_url}/login"
        st.link_button("🔗 Connect Google Calendar", login_url, use_container_width=True)
        st.stop()

    with st.sidebar:
        st.title("⚙️ Actions")
        st.text("Session Active")
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        display_upcoming_events()

    chat_col, calendar_col = st.columns([1, 1])

    with chat_col:
        st.subheader("💬 Chat")
        if not st.session_state.messages:
            st.session_state.messages.append({"content": "Hello! I'm connected to your calendar. How can I help?", "sender": "agent"})
            asyncio.run(fetch_upcoming_events())
            st.rerun()
        display_chat_history()

    with calendar_col:
        display_calendar_view()

    if user_input := st.chat_input("What can I help you with?"):
        asyncio.run(send_message_to_backend(user_input))
        asyncio.run(fetch_upcoming_events())
        st.rerun()

if __name__ == "__main__":
    main()