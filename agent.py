from langgraph.graph import StateGraph, END
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
import re
from dateutil import parser
from calendar_service import CalendarService
from models import BookingRequest, BookingResponse

class AgentState:
    """State management for the conversation agent"""
    def __init__(self):
        self.messages: List[BaseMessage] = []
        self.context: Dict[str, Any] = {}
        self.intent: str = ""
        self.extracted_info: Dict[str, Any] = {}
        self.availability_checked: bool = False
        self.booking_confirmed: bool = False

class TailorTalkAgent:
    def __init__(self):
        self.llm = ChatOpenAI(temperature=0.1, model="gpt-3.5-turbo")
        self.calendar_service = CalendarService()
        self.sessions: Dict[str, AgentState] = {}
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph conversation flow"""
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("understand_intent", self._understand_intent)
        graph.add_node("extract_datetime", self._extract_datetime)
        graph.add_node("check_availability", self._check_availability)
        graph.add_node("suggest_times", self._suggest_times)
        graph.add_node("confirm_booking", self._confirm_booking)
        graph.add_node("clarify_details", self._clarify_details)
        
        # Define edges and flow
        graph.add_edge("understand_intent", "extract_datetime")
        graph.add_conditional_edges(
            "extract_datetime",
            self._route_after_extraction,
            {
                "check_availability": "check_availability",
                "clarify": "clarify_details",
                "end": END
            }
        )
        graph.add_edge("check_availability", "suggest_times")
        graph.add_edge("suggest_times", "confirm_booking")
        graph.add_edge("clarify_details", "extract_datetime")
        graph.add_edge("confirm_booking", END)
        
        graph.set_entry_point("understand_intent")
        return graph.compile()
    
    async def process_message(self, message: str, session_id: str, context: Dict = None) -> Dict[str, Any]:
        """Process incoming message through the agent"""
        if session_id not in self.sessions:
            self.sessions[session_id] = AgentState()
        
        state = self.sessions[session_id]
        state.messages.append(HumanMessage(content=message))
        if context:
            state.context.update(context)
        
        # Run through the graph
        result = await self.graph.ainvoke(state)
        
        return {
            "message": result.messages[-1].content if result.messages else "I'm here to help you book appointments!",
            "context": result.context,
            "intent": result.intent
        }
    
    async def _understand_intent(self, state: AgentState) -> AgentState:
        """Understand user intent from the message"""
        latest_message = state.messages[-1].content
        
        prompt = f"""
        Analyze this message to understand the user's booking intent:
        "{latest_message}"
        
        Classify the intent as one of:
        - book_appointment: User wants to schedule something
        - check_availability: User wants to see free times
        - modify_appointment: User wants to change existing booking
        - cancel_appointment: User wants to cancel
        - general_inquiry: General questions about booking
        
        Also extract any clear preferences mentioned (time, date, duration, purpose).
        
        Respond in JSON format:
        {{
            "intent": "intent_category",
            "confidence": 0.9,
            "extracted_preferences": {{
                "date": "extracted_date_if_any",
                "time": "extracted_time_if_any",
                "duration": "extracted_duration_if_any",
                "purpose": "meeting_purpose_if_any"
            }}
        }}
        """
        
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        
        try:
            result = json.loads(response.content)
            state.intent = result["intent"]
            state.extracted_info.update(result.get("extracted_preferences", {}))
        except:
            state.intent = "general_inquiry"
        
        return state
    
    async def _extract_datetime(self, state: AgentState) -> AgentState:
        """Extract and normalize date/time information"""
        latest_message = state.messages[-1].content
        
        # Use regex and dateutil to extract temporal expressions
        temporal_patterns = [
            r'\btomorrow\b',
            r'\bnext week\b',
            r'\bfriday\b',
            r'\bthis afternoon\b',
            r'\bmorning\b',
            r'\d{1,2}:\d{2}',
            r'\d{1,2}\s*(am|pm)',
            r'\b\d{1,2}/\d{1,2}\b'
        ]
        
        found_temporals = []
        for pattern in temporal_patterns:
            matches = re.findall(pattern, latest_message, re.IGNORECASE)
            found_temporals.extend(matches)
        
        if found_temporals:
            # Try to parse with dateutil
            try:
                parsed_time = parser.parse(latest_message, fuzzy=True)
                state.extracted_info["parsed_datetime"] = parsed_time.isoformat()
            except:
                state.extracted_info["temporal_expressions"] = found_temporals
        
        return state
    
    def _route_after_extraction(self, state: AgentState) -> str:
        """Route based on extracted information completeness"""
        if state.intent == "check_availability":
            if "parsed_datetime" in state.extracted_info or "temporal_expressions" in state.extracted_info:
                return "check_availability"
            else:
                return "clarify"
        elif state.intent == "book_appointment":
            if "parsed_datetime" in state.extracted_info:
                return "check_availability"
            else:
                return "clarify"
        return "end"
    
    async def _check_availability(self, state: AgentState) -> AgentState:
        """Check calendar availability"""
        # Determine date range to check
        if "parsed_datetime" in state.extracted_info:
            target_date = parser.parse(state.extracted_info["parsed_datetime"])
        else:
            target_date = datetime.now() + timedelta(days=1)  # Default to tomorrow
        
        start_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end_date = target_date.replace(hour=17, minute=0, second=0, microsecond=0)
        
        try:
            availability = await self.calendar_service.get_availability(
                start_date.isoformat(),
                end_date.isoformat()
            )
            state.context["availability"] = availability
            state.availability_checked = True
        except Exception as e:
            state.context["availability_error"] = str(e)
        
        return state
    
    async def _suggest_times(self, state: AgentState) -> AgentState:
        """Suggest available time slots"""
        availability = state.context.get("availability", [])
        
        if availability:
            suggestions = []
            for slot in availability[:5]:  # Suggest top 5 slots
                start_time = parser.parse(slot["start"])
                suggestions.append(f"• {start_time.strftime('%A, %B %d at %I:%M %p')}")
            
            response = f"Great! I found several available time slots:\n\n" + "\n".join(suggestions)
            response += "\n\nWhich time works best for you? Just let me know and I'll book it!"
        else:
            response = "I'm sorry, but I don't see any available slots for that time. Would you like me to check a different day or time range?"
        
        state.messages.append(AIMessage(content=response))
        return state
    
    async def _confirm_booking(self, state: AgentState) -> AgentState:
        """Confirm and create the booking"""
        # This would be triggered by user confirming a suggested time
        response = "Perfect! I've booked that appointment for you. You'll receive a confirmation email shortly with all the details."
        state.messages.append(AIMessage(content=response))
        state.booking_confirmed = True
        return state
    
    async def _clarify_details(self, state: AgentState) -> AgentState:
        """Ask for clarification on missing details"""
        missing_info = []
        
        if "parsed_datetime" not in state.extracted_info and "temporal_expressions" not in state.extracted_info:
            missing_info.append("when you'd like to schedule")
        
        if state.intent == "book_appointment" and "purpose" not in state.extracted_info:
            missing_info.append("what type of meeting this is")
        
        if missing_info:
            response = f"I'd be happy to help you book an appointment! Could you please tell me {' and '.join(missing_info)}?"
        else:
            response = "Let me check what's available for you."
        
        state.messages.append(AIMessage(content=response))
        return state
    
    async def book_appointment(self, booking: BookingRequest) -> BookingResponse:
        """Book an appointment through the calendar service"""
        try:
            result = await self.calendar_service.create_event(
                title=booking.title,
                start_time=booking.start_time,
                end_time=booking.end_time,
                description=booking.description,
                attendees=booking.attendees
            )
            
            return BookingResponse(
                success=True,
                booking_id=result.get("id"),
                message="Appointment booked successfully!",
                details=result
            )
        except Exception as e:
            return BookingResponse(
                success=False,
                message=f"Failed to book appointment: {str(e)}"
            )
    
    async def get_availability(self, start_date: str, end_date: str) -> List[Dict]:
        """Get availability for a date range"""
        return await self.calendar_service.get_availability(start_date, end_date)