import streamlit as st
import httpx
import json
from datetime import datetime, timedelta
import uuid
from typing import List, Dict
import asyncio

# Configure the page
st.set_page_config(
    page_title="TailorTalk - AI Booking Assistant",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Initialize session state ---
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if 'messages' not in st.session_state:
    st.session_state.messages = []

# --- [THIS LINE WAS MISSING] ---
# Initialize the API base URL if it's not already in the session state
if 'api_base_url' not in st.session_state:
    st.session_state.api_base_url = "http://127.0.0.1:8000"


async def send_message(message: str) -> None:
    # This function remains unchanged
    if not message.strip():
        return
    
    st.session_state.messages.append({
        "content": message,
        "sender": "user",
        "timestamp": datetime.now()
    })
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{st.session_state.api_base_url}/chat",
                json={
                    "content": message,
                    "session_id": st.session_state.session_id,
                    "context": {},
                    "timestamp": datetime.now().isoformat()
                },
                timeout=30
            )
        
        if response.status_code == 200:
            agent_response = response.json()
            st.session_state.messages.append({
                "content": agent_response["content"],
                "sender": "agent",
                "timestamp": datetime.now(),
                "context": agent_response.get("context", {})
            })
        else:
            st.error(f"API Error: {response.status_code}")
            st.session_state.messages.append({
                "content": "Sorry, I'm having trouble connecting to my backend service. Please try again.",
                "sender": "agent",
                "timestamp": datetime.now()
            })
    
    except httpx.RequestError as e:
        st.error(f"Connection Error: {str(e)}")
        st.session_state.messages.append({
            "content": "I'm currently offline, but I'd be happy to help you book appointments when my service is back online!",
            "sender": "agent",
            "timestamp": datetime.now()
        })

async def book_slot(slot: Dict) -> None:
    # This function remains unchanged
    booking_message = f"I'd like to book the {datetime.fromisoformat(slot['start'].replace('Z', '+00:00')).strftime('%I:%M %p on %A, %B %d')} slot."
    await send_message(booking_message)

def display_message(message: Dict) -> None:
    # This function remains unchanged
    is_user = message["sender"] == "user"
    avatar = "🧑" if is_user else "🤖"
    
    with st.chat_message(name=message["sender"], avatar=avatar):
        st.markdown(message["content"])

def display_availability_slots(slots: List[Dict], message_index: int) -> None:
    # This function remains unchanged
    if not slots:
        return
    
    st.markdown("##### 📅 Available Time Slots")
    
    cols = st.columns(min(len(slots), 4))
    for i, slot in enumerate(slots[:8]):
        with cols[i % 4]:
            start_time = datetime.fromisoformat(slot["start"].replace('Z', '+00:00'))
            formatted_time = start_time.strftime("%I:%M %p")
            formatted_date = start_time.strftime("%a, %b %d")
            
            button_key = f"slot_{message_index}_{i}"
            
            if st.button(
                f"🕐 {formatted_time}\n_{formatted_date}_",
                key=button_key,
                help="Click to book this slot"
            ):
                asyncio.run(book_slot(slot))
                st.rerun()

def main():
    st.title("🤖 TailorTalk - AI Booking Assistant")
    st.markdown("*Your intelligent appointment scheduling companion*")

    with st.sidebar:
        st.title("⚙️ Configuration")
        # This line will now work correctly
        api_url = st.text_input("Backend API URL", value=st.session_state.api_base_url)
        st.session_state.api_base_url = api_url
        st.subheader("Session")
        st.text(f"Session ID: {st.session_state.session_id[:8]}...")
        if st.button("🔄 New Session"):
            # Clear messages and session_id, but api_base_url will be re-initialized at the top
            st.session_state.messages = []
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()

    # The rest of the main function remains unchanged
    if not st.session_state.messages:
        with st.chat_message(name="agent", avatar="🤖"):
            st.markdown("""
            👋 Hello! I'm TailorTalk, your AI booking assistant. I can help you:
            - 📅 Check your availability
            - 🕐 Schedule appointments
            - 📞 Book meetings and calls
            
            Just tell me what you need in natural language!
            """)

    for i, message in enumerate(st.session_state.messages):
        display_message(message)
        
        if message["sender"] == "agent" and "context" in message:
            context = message.get("context", {})
            if "availability" in context and context["availability"]:
                display_availability_slots(context["availability"], message_index=i)

    if user_input := st.chat_input("e.g., 'Do you have time tomorrow afternoon?'"):
        asyncio.run(send_message(user_input))
        st.rerun()


if __name__ == "__main__":
    main()