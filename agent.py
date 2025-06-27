# All initial imports remain the same...
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from typing import Dict, List, Any, TypedDict
from datetime import datetime, timedelta
import json
import re
from dateutil import parser
from calendar_service import CalendarService
from models import BookingRequest, BookingResponse

# AgentState and __init__ remain the same
class AgentState(TypedDict):
    messages: List[BaseMessage]
    context: Dict[str, Any]
    intent: str
    extracted_info: Dict[str, Any]
    availability_checked: bool
    booking_confirmed: bool
    final_booking_details: BookingRequest

class TailorTalkAgent:
    def __init__(self):
        self.llm = ChatOpenAI(temperature=0.1, model="gpt-3.5-turbo")
        self.calendar_service = CalendarService()
        self.sessions: Dict[str, AgentState] = {}
        self.initial_state = AgentState(
            messages=[], context={}, intent="", extracted_info={},
            availability_checked=False, booking_confirmed=False, final_booking_details=None
        )
        self.graph = self._build_graph()

    # The graph structure in _build_graph remains the same
    def _build_graph(self) -> StateGraph:
        # ... (no changes here)
        pass
    
    # process_message remains the same
    async def process_message(self, message: str, session_id: str, context: Dict = None) -> Dict[str, Any]:
        # ... (no changes here)
        pass

    # _route_after_extraction remains the same
    def _route_after_extraction(self, state: AgentState) -> str:
        # ... (no changes here)
        pass

    # --- [MODIFICATION] _confirm_booking now displays the raw API response ---
    async def _confirm_booking(self, state: AgentState) -> AgentState:
        """Confirm, create the booking, and show the API response."""
        response_message = ""
        try:
            booking_time_str = state['extracted_info'].get("parsed_datetime")
            start_time = parser.parse(booking_time_str)
            end_time = start_time + timedelta(minutes=30)

            booking_details = BookingRequest(
                title="Meeting Booked by TailorTalk AI",
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                description="This meeting was booked by the TailorTalk AI Assistant."
            )

            # Call the calendar service
            booking_response = await self.calendar_service.create_event(
                title=booking_details.title,
                start_time=booking_details.start_time,
                end_time=booking_details.end_time,
                description=booking_details.description
            )
            
            # Format the raw JSON response for display
            raw_response_json = json.dumps(booking_response, indent=2)
            
            if "error" in booking_response:
                 response_message = "I encountered an error trying to book the appointment.\n\n**Google Calendar API Response:**\n"
            else:
                response_message = "Success! The appointment has been booked in your Google Calendar.\n\n**Google Calendar API Response:**\n"
            
            response_message += f"```json\n{raw_response_json}\n```"
            state['booking_confirmed'] = True

        except Exception as e:
            response_message = f"An unexpected error occurred in the agent: {str(e)}"

        state['messages'].append(AIMessage(content=response_message))
        return state
        
    # _understand_intent and _extract_datetime remain the same
    async def _understand_intent(self, state: AgentState) -> AgentState:
        # ... (no changes here)
        pass

    async def _extract_datetime(self, state: AgentState) -> AgentState:
        # ... (no changes here)
        pass

    # --- [MODIFICATION] _suggest_times is updated to handle the raw freebusy response ---
    async def _suggest_times(self, state: AgentState) -> AgentState:
        """Suggest available time slots based on raw freebusy response."""
        freebusy_response = state['context'].get("availability", {})
        
        # Check for busy times in the primary calendar
        busy_times = freebusy_response.get('calendars', {}).get('primary', {}).get('busy', [])

        if not busy_times:
            response = "Your calendar appears to be completely free for the requested time. You can book any time."
        else:
            response = "I found some busy slots in your calendar. The raw free/busy response from Google is below. You can book a time that is not listed here.\n\n"
            response += "**Google Calendar API Response (Busy Times):**\n"
            response += f"```json\n{json.dumps(busy_times, indent=2)}\n```"

        state['messages'].append(AIMessage(content=response))
        return state
        
    # _clarify_details and _check_availability remain the same
    async def _clarify_details(self, state: AgentState) -> AgentState:
        # ... (no changes here)
        pass

    async def _check_availability(self, state: AgentState) -> AgentState:
        # ... (no changes here)
        pass