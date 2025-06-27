import streamlit as st
import requests
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

# Custom CSS for better styling
st.markdown("""
<style>
    .main {
        padding-top: 1rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        display: flex;
        align-items: flex-start;
    }
    .user-message, .agent-message {
        color: #222 !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .user-message {
        background-color: #e3f2fd;
        margin-left: 2rem;
    }
    .agent-message {
        background-color: #f5f5f5;
        margin-right: 2rem;
    }
    .message-avatar {
        width: 2rem;
        height: 2rem;
        border-radius: 50%;
        margin-right: 0.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
    }
    .user-avatar {
        background-color: #1976d2;
        color: white;
    }
    .agent-avatar {
        background-color: #4caf50;
        color: white;
    }
    .timestamp {
        font-size: 0.8rem;
        color: #666;
        margin-top: 0.25rem;
    }
    .booking-card {
        background-color: #fff3e0;
        border: 1px solid #ff9800;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .availability-slot {
        background-color: #e8f5e8;
        border: 1px solid #4caf50;
        border-radius: 0.25rem;
        padding: 0.5rem;
        margin: 0.25rem;
        cursor: pointer;
        transition: all 0.2s;
    }
    .availability-slot:hover {
        background-color: #c8e6c9;
        transform: translateY(-1px);
    }
    .stTextInput > div > input {
        background: #f8f9fa !important;
        color: #222 !important;
        border-radius: 0.5rem !important;
        border: 1px solid #ccc !important;
        padding: 0.5rem 1rem !important;
    }
    .stTextInput > div > input:focus {
        border: 1.5px solid #1976d2 !important;
        outline: none !important;
        box-shadow: 0 0 0 2px #1976d233 !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'api_base_url' not in st.session_state:
    st.session_state.api_base_url = "http://localhost:8000"

# Sidebar configuration
with st.sidebar:
    st.title("⚙️ Configuration")
    
    # API Configuration
    st.subheader("API Settings")
    api_url = st.text_input(
        "Backend API URL",
        value=st.session_state.api_base_url,
        help="URL of the TailorTalk FastAPI backend"
    )
    st.session_state.api_base_url = api_url
    
    # Session Management
    st.subheader("Session")
    st.text(f"Session ID: {st.session_state.session_id[:8]}...")
    
    if st.button("🔄 New Session"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    
    # Quick Actions
    st.subheader("Quick Actions")
    if st.button("📅 Check Today's Availability"):
        quick_message = "Do you have any availability today?"
        send_message(quick_message)
    
    if st.button("📞 Book Tomorrow Meeting"):
        quick_message = "I'd like to schedule a meeting tomorrow afternoon"
        send_message(quick_message)
    
    if st.button("🕐 Next Week Schedule"):
        quick_message = "What's available next week?"
        send_message(quick_message)
    
    # Statistics
    st.subheader("Chat Statistics")
    st.metric("Messages", len(st.session_state.messages))
    st.metric("Session Duration", f"{len(st.session_state.messages) * 2} min")

def send_message(message: str) -> None:
    """Send message to the backend API"""
    if not message.strip():
        return
    
    # Add user message to chat
    st.session_state.messages.append({
        "content": message,
        "sender": "user",
        "timestamp": datetime.now()
    })
    
    try:
        # Make API request
        response = requests.post(
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
            
            # Add agent response to chat
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
    
    except requests.exceptions.RequestException as e:
        st.error(f"Connection Error: {str(e)}")
        # Add fallback response
        st.session_state.messages.append({
            "content": "I'm currently offline, but I'd be happy to help you book appointments when my service is back online!",
            "sender": "agent",
            "timestamp": datetime.now()
        })

def display_message(message: Dict) -> None:
    """Display a chat message with styling"""
    is_user = message["sender"] == "user"
    
    # Create message container
    container_class = "user-message" if is_user else "agent-message"
    avatar_class = "user-avatar" if is_user else "agent-avatar"
    avatar_text = "U" if is_user else "AI"
    
    st.markdown(f"""
    <div class="chat-message {container_class}">
        <div class="message-avatar {avatar_class}">
            {avatar_text}
        </div>
        <div>
            <div>{message["content"]}</div>
            <div class="timestamp">
                {message["timestamp"].strftime("%H:%M")}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def display_availability_slots(slots: List[Dict]) -> None:
    """Display available time slots"""
    if not slots:
        return
    
    st.markdown("### 📅 Available Time Slots")
    
    cols = st.columns(min(len(slots), 3))
    for i, slot in enumerate(slots[:6]):  # Show max 6 slots
        with cols[i % 3]:
            start_time = datetime.fromisoformat(slot["start"].replace('Z', '+00:00'))
            formatted_time = start_time.strftime("%I:%M %p")
            formatted_date = start_time.strftime("%A, %b %d")
            
            if st.button(
                f"🕐 {formatted_time}\n📅 {formatted_date}",
                key=f"slot_{i}",
                help="Click to book this slot"
            ):
                book_slot(slot)

def book_slot(slot: Dict) -> None:
    """Book a selected time slot"""
    booking_message = f"I'd like to book the {datetime.fromisoformat(slot['start'].replace('Z', '+00:00')).strftime('%I:%M %p on %A, %B %d')} slot."
    send_message(booking_message)

# Main application
def main():
    st.title("🤖 TailorTalk - AI Booking Assistant")
    st.markdown("*Your intelligent appointment scheduling companion*")
    
    # Chat interface
    st.markdown("### 💬 Chat")
    
    # Display chat messages
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            # Welcome message
            st.markdown("""
            <div class="chat-message agent-message">
                <div class="message-avatar agent-avatar">AI</div>
                <div>
                    <div>👋 Hello! I'm TailorTalk, your AI booking assistant. I can help you:</div>
                    <ul>
                        <li>📅 Check your availability</li>
                        <li>🕐 Schedule appointments</li>
                        <li>📞 Book meetings and calls</li>
                        <li>📋 Manage your calendar</li>
                    </ul>
                    <div>Just tell me what you need in natural language!</div>
                    <div class="timestamp">Ready to help</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Display all messages
        for message in st.session_state.messages:
            display_message(message)
            
            # Display availability slots if present in context
            if message["sender"] == "agent" and "context" in message:
                context = message.get("context", {})
                if "availability" in context:
                    display_availability_slots(context["availability"])
    
    # Chat input
    st.markdown("---")
    
    # Create columns for input and send button
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_input = st.text_input(
            "Type your message...",
            placeholder="e.g., 'Do you have time tomorrow afternoon?' or 'Book a meeting next Friday'",
            key="user_input",
            label_visibility="collapsed"
        )
    
    with col2:
        send_button = st.button("Send 📤", use_container_width=True)
    
    # Handle message sending
    if send_button or (user_input and st.session_state.get("enter_pressed", False)):
        if user_input.strip():
            send_message(user_input)
            st.rerun()
    
    # Handle Enter key press
    if user_input:
        st.markdown("""
        <script>
        const input = document.querySelector('input[aria-label="Type your message..."]');
        if (input) {
            input.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    window.parent.postMessage({type: 'streamlit:setComponentValue', key: 'enter_pressed', value: true}, '*');
                }
            });
        }
        </script>
        """, unsafe_allow_html=True)
    
    # Sample interactions section
    st.markdown("---")
    st.markdown("### 💡 Try These Sample Interactions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **📅 Check Availability**
        - "What's free tomorrow?"
        - "Any slots this Friday?"
        - "Available next week?"
        """)
    
    with col2:
        st.markdown("""
        **📞 Book Meetings**  
        - "Schedule a call at 3 PM"
        - "Book lunch meeting tomorrow"
        - "Set up client call next Monday"
        """)
    
    with col3:
        st.markdown("""
        **🕐 Flexible Booking**
        - "Need 30 mins sometime today"
        - "Book between 2-4 PM Friday"
        - "Schedule team meeting next week"
        """)
    
    # Quick action buttons
    st.markdown("### ⚡ Quick Actions")
    
    action_col1, action_col2, action_col3, action_col4 = st.columns(4)
    
    with action_col1:
        if st.button("📅 Today's Schedule", use_container_width=True):
            send_message("What's my schedule for today?")
            st.rerun()
    
    with action_col2:
        if st.button("🕐 Tomorrow Free?", use_container_width=True):
            send_message("Do you have any free time tomorrow?")
            st.rerun()
    
    with action_col3:
        if st.button("📞 Book Call", use_container_width=True):
            send_message("I need to schedule a call this week")
            st.rerun()
    
    with action_col4:
        if st.button("📋 Next Week", use_container_width=True):
            send_message("What's available next week?")
            st.rerun()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9rem;'>
        🤖 TailorTalk AI Booking Assistant | Built with FastAPI, LangGraph & Streamlit
    </div>
    """, unsafe_allow_html=True)

# Run the main function
if __name__ == "__main__":
    main()