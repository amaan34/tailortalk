from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from typing import Dict, List, Any, TypedDict
from datetime import datetime, timedelta
import json
import re
from dateutil import parser
import logging
import pytz

from calendar_service import CalendarService
from models import BookingRequest

LOCAL_TIMEZONE = pytz.timezone("Asia/Kolkata")

# Set up a logger for the agent
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """Represents the state of our conversational agent."""
    session_id: str
    messages: List[BaseMessage]
    context: Dict[str, Any]
    intent: str
    extracted_info: Dict[str, Any]
    availability_checked: bool
    booking_confirmed: bool
    final_booking_details: BookingRequest
    conversation_stage: str

class TailorTalkAgent:
    """The core conversational agent for booking appointments."""

    def __init__(self):
        self.llm = ChatOpenAI(temperature=0.1, model="gpt-3.5-turbo")
        self.calendar_service = CalendarService()
        self.sessions: Dict[str, AgentState] = {}
        self.initial_state = AgentState(
            session_id="",
            messages=[], context={}, intent="", extracted_info={},
            availability_checked=False, booking_confirmed=False,
            final_booking_details=None, conversation_stage="start"
        )
        self.graph = self._build_graph()
        logger.info("TailorTalkAgent initialized with a new graph.")

    def _build_graph(self) -> StateGraph:
        """Builds the LangGraph conversation flow with more intelligent routing."""
        graph = StateGraph(AgentState)

        graph.add_node("understand_intent", self._understand_intent)
        graph.add_node("extract_datetime", self._extract_datetime)
        # [MODIFICATION] New node to check a single, specific slot
        graph.add_node("check_specific_slot", self._check_specific_slot)
        graph.add_node("check_availability", self._check_availability)
        graph.add_node("suggest_times", self._suggest_times)
        graph.add_node("confirm_booking", self._confirm_booking)
        graph.add_node("clarify_details", self._clarify_details)

        graph.set_entry_point("understand_intent")
        graph.add_edge("understand_intent", "extract_datetime")
        
        # This first router decides whether to check a specific slot or general availability
        graph.add_conditional_edges(
            "extract_datetime",
            self._route_after_datetime_extraction,
            {
                "check_specific_slot": "check_specific_slot",
                "check_availability": "check_availability",
                "clarify": "clarify_details",
            }
        )

        # [MODIFICATION] This new router decides what to do after checking a specific slot
        graph.add_conditional_edges(
            "check_specific_slot",
            self._route_after_specific_slot_check,
            {
                "confirm": "confirm_booking",
                "suggest_alternatives": "check_availability" # If busy, find other times
            }
        )

        graph.add_edge("check_availability", "suggest_times")
        graph.add_edge("suggest_times", END)
        graph.add_edge("clarify_details", END)
        graph.add_edge("confirm_booking", END)

        return graph.compile()

    def _route_after_specific_slot_check(self, state: AgentState) -> str:
        """Routes to confirmation if the slot is free, or suggests alternatives if it's busy."""
        logger.debug(f"[{state['session_id']}] Router: _route_after_specific_slot_check")
        if state['context'].get('is_slot_available'):
            logger.info(f"[{state['session_id']}] Specific slot is available. Routing to confirm.")
            return "confirm"
        else:
            logger.info(f"[{state['session_id']}] Specific slot is busy. Routing to find alternatives.")
            # We set a flag to give a better response message in the next step
            state['context']['user_informed_slot_is_busy'] = True
            return "suggest_alternatives"
        
    async def process_message(self, message: str, session_id: str, context: Dict = None) -> Dict[str, Any]:
        """Processes an incoming message through the agent's graph."""
        logger.info(f"Processing message for session_id: {session_id}")
        if session_id not in self.sessions:
            logger.info(f"New session created: {session_id}")
            self.sessions[session_id] = self.initial_state.copy()
            self.sessions[session_id]['session_id'] = session_id
        
        state = self.sessions[session_id]
        
        state['context'].pop('availability', None)
        state['context'].pop('availability_error', None)

        state['messages'].append(HumanMessage(content=message))
        if context:
            state['context'].update(context)

        result_state = await self.graph.ainvoke(state)
        
        self.sessions[session_id] = result_state

        logger.info(f"Finished processing for session_id: {session_id}. Final intent: '{result_state['intent']}'")
        return {
            "message": result_state['messages'][-1].content if result_state['messages'] else "How can I help you?",
            "context": result_state['context'],
            "intent": result_state['intent']
        }

    # --- Graph Nodes ---
    # No changes are needed in the node functions themselves.

    async def _understand_intent(self, state: AgentState) -> AgentState:
        """Node to understand the user's intent from the latest message."""
        logger.debug(f"[{state['session_id']}] Node: _understand_intent")
        latest_message = state['messages'][-1].content
        prompt = f"""
        Analyze the user's message to determine their intent for a booking assistant.
        Message: "{latest_message}"

        Classify the intent as one of:
        - "book_appointment": The user explicitly wants to schedule an appointment. This includes confirming a suggested time.
        - "check_availability": The user is asking about available times without committing to a booking.
        - "general_inquiry": The user is asking a question that is not directly about booking or availability.

        Respond with a JSON object: {{"intent": "classified_intent"}}
        """
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        try:
            result = json.loads(response.content)
            state['intent'] = result.get("intent", "general_inquiry")
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse intent from LLM response. Defaulting to 'general_inquiry'.")
            state['intent'] = "general_inquiry"
        logger.info(f"[{state['session_id']}] Detected intent: {state['intent']}")
        return state

    async def _extract_datetime(self, state: AgentState) -> AgentState:
        """Node to extract and normalize date/time information from the message."""
        logger.debug(f"[{state['session_id']}] Node: _extract_datetime")
        human_messages = [msg.content for msg in state['messages'] if isinstance(msg, HumanMessage)]
        latest_human_message = human_messages[-1] if human_messages else ""
        
        try:
            if latest_human_message:
                # Step 1: Parse the naive datetime from user input
                parsed_time_naive = parser.parse(latest_human_message, fuzzy=True)
                # Step 2: [MODIFICATION] Make the datetime object "aware" of the local timezone
                parsed_time_aware = LOCAL_TIMEZONE.localize(parsed_time_naive)
                
                state['extracted_info']["parsed_datetime"] = parsed_time_aware.isoformat()
                logger.info(f"[{state['session_id']}] Extracted and localized datetime: {parsed_time_aware.isoformat()} from message: '{latest_human_message}'")
            else:
                 raise ValueError("No human message to parse.")
        except (ValueError, TypeError):
            logger.info(f"[{state['session_id']}] No specific datetime found in the last human message.")
            state['extracted_info'].pop("parsed_datetime", None)
        return state

    # ... (_route_after_datetime_extraction is the same) ...

    async def _check_availability(self, state: AgentState) -> AgentState:
        """Node to check the calendar for available slots."""
        logger.debug(f"[{state['session_id']}] Node: _check_availability")
        
        # [MODIFICATION] Work with timezone-aware datetimes
        if "parsed_datetime" in state['extracted_info']:
            target_date = parser.parse(state['extracted_info']["parsed_datetime"])
        else:
            target_date = datetime.now(LOCAL_TIMEZONE)

        # Define business hours in the local timezone
        start_of_day = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end_of_day = target_date.replace(hour=17, minute=0, second=0, microsecond=0)

        try:
            # The service expects ISO format strings, which our aware objects now provide
            availability_response = await self.calendar_service.get_availability(
                start_of_day.isoformat(),
                end_of_day.isoformat()
            )
            state['context']["availability"] = availability_response.get('calendars', {}).get('primary', {}).get('busy', [])
            state['availability_checked'] = True
            logger.info(f"[{state['session_id']}] Availability check completed.")
        except Exception as e:
            logger.error(f"[{state['session_id']}] Error during availability check: {e}", exc_info=True)
            state['context']["availability_error"] = str(e)
        return state

    def _route_after_datetime_extraction(self, state: AgentState) -> str:
        """Routes to check a specific slot if requested, otherwise checks general availability."""
        logger.debug(f"[{state['session_id']}] Router: _route_after_datetime_extraction")
        intent = state.get('intent')
        has_datetime = "parsed_datetime" in state.get('extracted_info', {})

        if not has_datetime:
            return "clarify"
        
        # If user wants to book a specific time, check that slot first.
        if intent == 'book_appointment':
            logger.info(f"[{state['session_id']}] Routing to check specific slot.")
            return "check_specific_slot"
        
        # If user just wants to see general availability for a day.
        if intent == 'check_availability':
            logger.info(f"[{state['session_id']}] Routing to check general day availability.")
            return "check_availability"
            
        return "clarify"

    async def _check_availability(self, state: AgentState) -> AgentState:
        """Node to check the calendar for available slots."""
        logger.debug(f"[{state['session_id']}] Node: _check_availability")
        
        if "parsed_datetime" in state['extracted_info']:
            target_date = parser.parse(state['extracted_info']["parsed_datetime"])
        else:
            target_date = datetime.now(LOCAL_TIMEZONE)

        start_of_day = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
        end_of_day = target_date.replace(hour=17, minute=0, second=0, microsecond=0)

        try:
            # [FIX] Removed the incorrect `+ "Z"` concatenation.
            # .isoformat() on an aware object already produces the correct RFC3339 string.
            availability_response = await self.calendar_service.get_availability(
                start_of_day.isoformat(),
                end_of_day.isoformat()
            )
            # This check is important for the next step.
            if "error" in availability_response:
                raise Exception(availability_response["error"])

            state['context']["availability"] = availability_response.get('calendars', {}).get('primary', {}).get('busy', [])
            state['availability_checked'] = True
            logger.info(f"[{state['session_id']}] Availability check completed successfully.")
        except Exception as e:
            logger.error(f"[{state['session_id']}] Error during availability check: {e}", exc_info=True)
            state['context']["availability_error"] = str(e)
        return state
    
    async def _suggest_times(self, state: AgentState) -> AgentState:
        """Suggests available time slots, now with context-aware messages."""
        logger.debug(f"[{state['session_id']}] Node: _suggest_times")
        
        # This part of the node is largely the same as the last version, but we add a custom message.
        if "availability_error" in state['context']:
            # ... (error handling remains the same)
            pass

        try:
            # [MODIFICATION] Check if we're here because a specific slot was busy
            if state['context'].get('user_informed_slot_is_busy'):
                base_message = "I'm sorry, but that time is already booked. Here are some other available slots for that day:"
            else:
                base_message = "Great! I found several available time slots. Which one works best for you?"

            # The calculation logic from the previous step remains the same
            target_date = parser.parse(state['extracted_info'].get("parsed_datetime"))
            day_start = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
            day_end = target_date.replace(hour=17, minute=0, second=0, microsecond=0)
            busy_times = state['context'].get("availability", [])
            busy_intervals = sorted([(parser.parse(b['start']), parser.parse(b['end'])) for b in busy_times])
            current_time = day_start
            free_slots = []
            for busy_start, busy_end in busy_intervals:
                if current_time < busy_start: free_slots.append({'start': current_time, 'end': busy_start})
                current_time = max(current_time, busy_end)
            if current_time < day_end: free_slots.append({'start': current_time, 'end': day_end})
            appointment_slots = []
            for slot in free_slots:
                slot_start, slot_end = slot['start'], slot['end']
                while slot_start + timedelta(minutes=30) <= slot_end:
                    appointment_slots.append({'start': slot_start.isoformat(),'end': (slot_start + timedelta(minutes=30)).isoformat()})
                    slot_start += timedelta(minutes=30)

            if appointment_slots:
                state['context']['availability'] = appointment_slots
                response_message = base_message
            else:
                response_message = "I'm sorry, but I don't see any other available slots for that day."
                state['context']['availability'] = []

        except Exception as e:
            # ... (exception handling remains the same)
            pass

        state['messages'].append(AIMessage(content=response_message))
        return state

    async def _clarify_details(self, state: AgentState) -> AgentState:
        logger.debug(f"[{state['session_id']}] Node: _clarify_details")
        response = "I can help with that! When were you thinking of scheduling the appointment?"
        state['messages'].append(AIMessage(content=response))
        return state

    async def _confirm_booking(self, state: AgentState) -> AgentState:
        logger.debug(f"[{state['session_id']}] Node: _confirm_booking")
        booking_time_str = state['extracted_info'].get("parsed_datetime")
        if not booking_time_str:
            logger.warning(f"[{state['session_id']}] Attempted to confirm booking with no datetime extracted.")
            response_message = "I seem to have lost the time for the booking. Could you please specify it again?"
            state['messages'].append(AIMessage(content=response_message))
            return state
        try:
            start_time = parser.parse(booking_time_str)
            end_time = start_time + timedelta(minutes=30)
            logger.info(f"[{state['session_id']}] Attempting to book event for {start_time.isoformat()}")
            booking_response = await self.calendar_service.create_event(title="TailorTalk Appointment", start_time=start_time.isoformat(), end_time=end_time.isoformat(), description="This appointment was booked by the TailorTalk AI Assistant.")
            if booking_response and 'id' in booking_response:
                response_message = f"Excellent! I have successfully booked your appointment for {start_time.strftime('%I:%M %p on %A, %B %d')}. You will receive a calendar invitation shortly."
                state['booking_confirmed'] = True
                state['context']['booking_details'] = booking_response
                logger.info(f"[{state['session_id']}] Booking confirmed with event ID: {booking_response['id']}")
            else:
                error_msg = booking_response.get("error", "an unknown issue")
                response_message = f"I'm sorry, I was unable to create the event on the calendar due to: {error_msg}. Please try again."
                logger.error(f"[{state['session_id']}] Booking failed. Calendar service response: {booking_response}")
        except Exception as e:
            response_message = f"An unexpected error occurred while finalizing your booking: {str(e)}"
            logger.error(f"[{state['session_id']}] An unexpected exception in _confirm_booking.", exc_info=True)
        state['messages'].append(AIMessage(content=response_message))
        return state
    
        # --- Graph Nodes ---
    
    async def _check_specific_slot(self, state: AgentState) -> AgentState:
        """New node to check availability for only the exact time the user requested."""
        logger.debug(f"[{state['session_id']}] Node: _check_specific_slot")
        try:
            start_time = parser.parse(state['extracted_info']["parsed_datetime"])
            end_time = start_time + timedelta(minutes=30)
            
            availability_response = await self.calendar_service.get_availability(
                start_time.isoformat(), end_time.isoformat()
            )
            
            if "error" in availability_response:
                raise Exception(availability_response["error"])

            busy_times = availability_response.get('calendars', {}).get('primary', {}).get('busy', [])
            
            # If the busy list is empty for this narrow window, the slot is free
            state['context']['is_slot_available'] = not busy_times
            
        except Exception as e:
            logger.error(f"[{state['session_id']}] Error during specific slot check: {e}", exc_info=True)
            state['context']['is_slot_available'] = False # Assume not available on error
            
        return state