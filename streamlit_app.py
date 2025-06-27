import streamlit as st
import httpx
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
from streamlit_calendar import calendar # Import the new component

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
    if 'pending_action' not in st.session_state:
        st.session_state.pending_action = None
    if 'upcoming_events' not in st.session_state:
        st.session_state.upcoming_events = []

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

def handle_slot_booking(slot: Dict[str, Any]):
    """Sets the booking confirmation message as a pending action."""
    start_time_obj = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
    booking_message = f"Yes, please book the {start_time_obj.strftime('%I:%M %p on %A, %B %d')} slot."
    st.session_state.pending_action = booking_message

def handle_event_action(action: str, event: Dict[str, Any]):
    """Sets a cancel or reschedule action as pending."""
    event_summary = event.get('summary', 'your event')
    start_time_str = event.get('start', {}).get('dateTime')
    start_time_obj = datetime.fromisoformat(start_time_str)
    
    if action == "cancel":
        action_message = f"I need to cancel my appointment '{event_summary}' on {start_time_obj.strftime('%A, %B %d at %I:%M %p')}."
    elif action == "reschedule":
        action_message = f"I'd like to reschedule my event '{event_summary}' on {start_time_obj.strftime('%A, %B %d at %I:%M %p')}."

    st.session_state.pending_action = action_message

async def fetch_upcoming_events():
    """Fetches the next 7 days of events from the backend."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{st.session_state.api_base_url}/events")
            response.raise_for_status()
            st.session_state.upcoming_events = response.json()
    except Exception as e:
        st.sidebar.error(f"Could not fetch events: {e}")
        st.session_state.upcoming_events = []


# --- UI Display Functions ---
def display_chat_history():
    """Displays all messages and action buttons."""
    for i, msg in enumerate(st.session_state.messages):
        avatar = "🧑" if msg["sender"] == "user" else "🤖"
        with st.chat_message(name=msg["sender"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["sender"] == "agent" and "availability" in msg.get("context", {}):
                display_availability_buttons(msg["context"]["availability"], message_index=i)

def display_upcoming_events():
    """Displays upcoming events in the sidebar."""
    st.sidebar.subheader("🗓️ Upcoming Events")
    if st.sidebar.button("🔄 Refresh Events"):
        asyncio.run(fetch_upcoming_events())
        st.rerun()

    if not st.session_state.upcoming_events:
        st.sidebar.info("No upcoming events found.")
        return

    for event in st.session_state.upcoming_events[:7]:
        summary = event.get('summary', 'No Title')
        start_time = datetime.fromisoformat(event['start'].get('dateTime')).strftime('%a, %b %d, %I:%M %p')
        
        with st.sidebar.expander(f"**{summary}** at {start_time}"):
            st.button(
                "❌ Cancel", 
                key=f"cancel_{event['id']}", 
                on_click=handle_event_action, 
                args=("cancel", event)
            )
            # Reschedule button can be added here with similar logic
            st.button(
                "🔄 Reschedule", 
                key=f"reschedule_{event['id']}", 
                on_click=handle_event_action, 
                args=("reschedule", event)
            )
def display_calendar_view():
    """Renders the visual calendar component."""
    st.subheader("My Calendar View")
    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay",
        },
    }
    calendar_events = []
    for event in st.session_state.upcoming_events:
        calendar_events.append({
            "title": event.get("summary", "No Title"),
            "start": event.get("start", {}).get("dateTime"),
            "end": event.get("end", {}).get("dateTime"),
        })

    calendar(events=calendar_events, options=calendar_options)
          

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

    with st.sidebar:
        st.title("⚙️ Configuration & Actions")
        api_url = st.text_input("Backend API URL", value=st.session_state.api_base_url)
        st.session_state.api_base_url = api_url
        if st.button("🔄 Start New Conversation"):
            st.session_state.clear()
            initialize_session_state()
            st.rerun()
        
        display_upcoming_events()

    # Main area layout
    chat_col, calendar_col = st.columns([1, 1])

    with chat_col:
        st.subheader("💬 Chat")
        if not st.session_state.messages:
            st.session_state.messages.append({
                "content": "👋 Hello! I'm TailorTalk. You can ask me to book, cancel, or reschedule appointments.",
                "sender": "agent", "timestamp": datetime.now()
            })
            # Fetch events on first load
            asyncio.run(fetch_upcoming_events())

        display_chat_history()

    with calendar_col:
        display_calendar_view()

    # Handle pending actions at the top of the script run
    if st.session_state.pending_action:
        action = st.session_state.pending_action
        st.session_state.pending_action = None # Clear the action
        asyncio.run(send_message_to_backend(action))
        # After action, refresh events and rerun
        asyncio.run(fetch_upcoming_events())
        st.rerun()

    if user_input := st.chat_input("What can I help you with?"):
        asyncio.run(send_message_to_backend(user_input))
        asyncio.run(fetch_upcoming_events()) # Refresh after user interaction
        st.rerun()

if __name__ == "__main__":
    main()