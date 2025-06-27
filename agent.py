from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from typing import Dict, List, Any, TypedDict, Optional
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
    cancellation_candidates: List[Dict]
    event_to_reschedule: Optional[Dict]
    suggested_slots: List[Dict]
class TailorTalkAgent:
    """The core conversational agent for booking appointments."""

    def __init__(self):
        self.llm = ChatOpenAI(temperature=0.1, model="gpt-3.5-turbo")
        self.sessions: Dict[str, AgentState] = {}
        self.initial_state = AgentState(
            session_id="",
            messages=[], context={}, intent="", extracted_info={},
            availability_checked=False, booking_confirmed=False,
            final_booking_details=None, conversation_stage="start",
            cancellation_candidates=[], event_to_reschedule=None,
            suggested_slots=[]
        )
        self.graph = self._build_graph()
        logger.info("TailorTalkAgent initialized with a new graph.")

    def _build_graph(self) -> StateGraph:
        """Builds the LangGraph conversation flow with more intelligent routing."""
        graph = StateGraph(AgentState)

        graph.set_entry_point("initial_router")

        # Add nodes
        graph.add_node("initial_router", self._initial_router)
        graph.add_node("understand_intent", self._understand_intent)
        graph.add_node("extract_datetime", self._extract_datetime)
        graph.add_node("check_specific_slot", self._check_specific_slot)
        graph.add_node("check_availability", self._check_availability)
        graph.add_node("suggest_times", self._suggest_times)
        graph.add_node("confirm_booking", self._confirm_booking)
        graph.add_node("clarify_details", self._clarify_details)
        graph.add_node("find_event_for_action", self._find_event_for_action)
        graph.add_node("handle_cancellation", self._handle_cancellation)
        graph.add_node("clarify_cancellation", self._clarify_cancellation)
        graph.add_node("handle_reschedule_request", self._handle_reschedule_request)
        graph.add_node("complete_reschedule", self._complete_reschedule)
        graph.add_node("list_found_events", self._list_found_events)
        graph.add_node("handle_general_inquiry", self._handle_general_inquiry)

        # Define graph edges
        graph.add_conditional_edges(
            "initial_router",
            lambda state: "complete_reschedule" if state.get('event_to_reschedule') else "understand_intent",
            {
                "complete_reschedule": "complete_reschedule",
                "understand_intent": "understand_intent"
            }
        )

        graph.add_edge("complete_reschedule", END)

        graph.add_conditional_edges(
            "understand_intent",
            self._route_by_intent,
            {
                "find_event": "find_event_for_action",
                "book": "extract_datetime",
                "check": "extract_datetime",
                "cancel": "find_event_for_action",
                "reschedule": "find_event_for_action",
                "general_inquiry": "handle_general_inquiry",
                "clarify": "clarify_details"
            }
        )

        graph.add_conditional_edges(
            "extract_datetime",
            self._route_after_datetime_extraction,
            {
                "check_specific_slot": "check_specific_slot",
                "check_availability": "check_availability",
                "clarify": "clarify_details",
            }
        )

        graph.add_conditional_edges(
            "check_specific_slot",
            self._route_after_specific_slot_check,
            {
                "confirm": "confirm_booking",
                "suggest_alternatives": "check_availability"
            }
        )

        graph.add_conditional_edges(
            "find_event_for_action",
            self._route_after_event_search,
            {
                "list_events": "list_found_events",
                "cancel": "handle_cancellation",
                "reschedule": "handle_reschedule_request",
                "clarify_cancel": "clarify_cancellation",
                "not_found": "list_found_events"
            }
        )

        graph.add_edge("list_found_events", END)
        graph.add_edge("check_availability", "suggest_times")
        graph.add_edge("suggest_times", END)
        graph.add_edge("clarify_details", END)
        graph.add_edge("clarify_cancellation", END)
        graph.add_edge("handle_cancellation", END)
        graph.add_edge("handle_reschedule_request", END)
        graph.add_edge("confirm_booking", END)
        graph.add_edge("handle_general_inquiry", END)


        return graph.compile()

    async def _initial_router(self, state: AgentState) -> AgentState:
        """Acts as a gatekeeper to route to special handlers if a multi-turn process is active."""
        logger.debug(f"[{state['session_id']}] Node: _initial_router. Checking for ongoing reschedule.")
        return state

    async def _handle_reschedule_request(self, state: AgentState) -> AgentState:
        """Handles the FIRST step of a reschedule request: identifying the event and asking for the new time."""
        logger.debug(f"[{state['session_id']}] Node: _handle_reschedule_request")
        
        event_to_reschedule = state['cancellation_candidates'][0]
        state['event_to_reschedule'] = event_to_reschedule
        
        response_message = f"I can help with that. I've found the event '{event_to_reschedule.get('summary')}'. When were you thinking of rescheduling the appointment?"
        state['messages'].append(AIMessage(content=response_message))
        return state
        
    async def _complete_reschedule(self, state: AgentState, config: dict) -> AgentState:
        calendar_service: CalendarService = config["configurable"]["calendar_service"]
        """Handles the SECOND step of rescheduling: processing the user's new desired time."""
        logger.debug(f"[{state['session_id']}] Node: _complete_reschedule")
        
        original_event = state['event_to_reschedule']
        latest_message = state['messages'][-1].content
        
        await self._extract_datetime(state)
        new_time_str = state['extracted_info'].get("parsed_datetime")

        if not new_time_str:
            response_message = "I'm sorry, I didn't understand that time. Could you please provide the new date and time for the reschedule?"
            state['messages'].append(AIMessage(content=response_message))
            return state

        new_start_time = parser.parse(new_time_str)
        
        # Calculate event duration from original event, default to 30 mins if not available
        try:
            original_start = parser.parse(original_event['start']['dateTime'])
            original_end = parser.parse(original_event['end']['dateTime'])
            duration = original_end - original_start
        except (KeyError, TypeError):
            duration = timedelta(minutes=30)
        
        new_end_time = new_start_time + duration
        
        availability_response = await self.calendar_service.get_availability(
            new_start_time.isoformat(), new_end_time.isoformat()
        )
        busy_times = availability_response.get('calendars', {}).get('primary', {}).get('busy', [])

        if busy_times:
            response_message = f"I'm sorry, but that time is already booked. Please suggest another time for rescheduling '{original_event.get('summary')}'."
            state['messages'].append(AIMessage(content=response_message))
            return state

        event_id = original_event['id']
        update_body = {
            'summary': original_event.get('summary'),
            'description': original_event.get('description'),
            'start': {'dateTime': new_start_time.isoformat(), 'timeZone': str(LOCAL_TIMEZONE)},
            'end': {'dateTime': new_end_time.isoformat(), 'timeZone': str(LOCAL_TIMEZONE)},
            'attendees': original_event.get('attendees', [])
        }
        
        update_response = await self.calendar_service.update_event(event_id, update_body)

        if "error" in update_response:
            response_message = f"I'm sorry, an error occurred while trying to update the event: {update_response['error']}"
        else:
            formatted_time = new_start_time.strftime('%I:%M %p on %A, %B %d')
            response_message = f"Excellent! I have successfully rescheduled your appointment to {formatted_time}."
            state['event_to_reschedule'] = None
            state['cancellation_candidates'] = []

        state['messages'].append(AIMessage(content=response_message))
        return state

    async def _handle_reschedule(self, state: AgentState) -> AgentState:
        """Handles the logic for rescheduling an event."""
        logger.debug(f"[{state['session_id']}] Node: _handle_reschedule")
        # This is a simplified version. A full implementation would be a sub-graph:
        # 1. Confirm the event to reschedule (done by the router before this node).
        # 2. Extract the NEW desired time from the user's message.
        # 3. Check availability for the new time.
        # 4. If free, call update_event. If not, suggest alternatives.
        
        event_to_reschedule = state['cancellation_candidates'][0]
        state['event_to_reschedule'] = event_to_reschedule
        
        # For now, we just ask for the new time.
        response_message = f"Okay, I'm ready to reschedule '{event_to_reschedule.get('summary')}'. What's the new time you'd like?"
        state['messages'].append(AIMessage(content=response_message))
        # The next turn of conversation would be handled by the graph again.
        return state
    
    async def _clarify_cancellation(self, state: AgentState) -> AgentState:
        """Asks the user to clarify which event to cancel from a list."""
        logger.debug(f"[{state['session_id']}] Node: _clarify_cancellation")
        candidates = state['cancellation_candidates']
        options = []
        for event in candidates:
            start_time = parser.parse(event['start'].get('dateTime')).strftime('%I:%M %p')
            options.append(f"'{event['summary']}' at {start_time}")
        
        message = "I found a few events that match. Which one did you mean?\n- " + "\n- ".join(options)
        state['messages'].append(AIMessage(content=message))
        return state

    async def _handle_cancellation(self, state: AgentState, config: dict) -> AgentState:
        calendar_service: CalendarService = config["configurable"]["calendar_service"]
        """Deletes the confirmed event."""
        logger.debug(f"[{state['session_id']}] Node: _handle_cancellation")
        event_to_cancel = state['cancellation_candidates'][0]
        event_id = event_to_cancel.get('id')
        summary = event_to_cancel.get('summary', 'your appointment')

        result = await self.calendar_service.delete_event(event_id)

        if "error" in result:
            response_message = f"I'm sorry, I failed to cancel '{summary}'. Error: {result['error']}"
        else:
            response_message = f"Done. I have successfully cancelled your event: '{summary}'."
        
        state['messages'].append(AIMessage(content=response_message))
        return state
    
    
    def _route_by_intent(self, state: AgentState) -> str:
        """Routes based on the primary classified intent."""
        intent = state.get('intent')
        if intent == 'find_event':
            return "find_event"
        if intent == 'book_appointment':
            return "book"
        if intent == 'check_availability':
            return "check"
        if intent == 'cancel_appointment':
            return "cancel"
        if intent == 'reschedule_appointment':
            return "reschedule"
        if intent == 'general_inquiry':
            return "general_inquiry"
        return "clarify"
    
    async def _handle_general_inquiry(self, state: AgentState) -> AgentState:
        """Handles general inquiries with a more appropriate response."""
        logger.debug(f"[{state['session_id']}] Node: _handle_general_inquiry")
        response = "I can help with booking, canceling, and rescheduling appointments. How can I assist you today?"
        state['messages'].append(AIMessage(content=response))
        return state
    
    
    def _route_after_event_search(self, state: AgentState) -> str:
        """Routes after searching for an event to cancel or reschedule."""
        num_candidates = len(state.get('cancellation_candidates', []))
        intent = state.get('intent')

        if intent == 'find_event':
            return "list_events"

        if num_candidates == 0:
            state['messages'].append(AIMessage(content="I couldn't find any event matching that description. Could you be more specific?"))
            return "not_found"
        if num_candidates > 1:
            return "clarify_cancel"

        if intent == 'cancel_appointment':
            return "cancel"
        if intent == 'reschedule_appointment':
            return "reschedule"
        return "not_found"

    async def _find_event_for_action(self, state: AgentState, config: dict) -> AgentState:
        calendar_service: CalendarService = config["configurable"]["calendar_service"]
        """Finds calendar events based on the user's message, now with whole-day search."""
        logger.debug(f"[{state['session_id']}] Node: _find_event_for_action")
        
        await self._extract_datetime(state)
        parsed_time_str = state['extracted_info'].get("parsed_datetime")

        if not parsed_time_str:
            state['messages'].append(AIMessage("I'm not sure which day you're asking about. Please specify a date."))
            state['cancellation_candidates'] = []
            return state

        target_dt = parser.parse(parsed_time_str)

        # [MODIFICATION] Smarter time window selection
        # If the user's query didn't specify a time, search the whole day
        if target_dt.hour == 0 and target_dt.minute == 0:
            start_time = target_dt.isoformat()
            end_time = (target_dt + timedelta(days=1, microseconds=-1)).isoformat()
            logger.info(f"Searching for whole day: {target_dt.date()}")
        else:
            # If they specified a time, use the original windowed search
            start_time = (target_dt - timedelta(hours=2)).isoformat()
            end_time = (target_dt + timedelta(hours=2)).isoformat()
            logger.info(f"Searching in a window around: {target_dt}")

        events_response = await self.calendar_service.search_events(start_time, end_time)
        
        if "error" in events_response:
            state['messages'].append(AIMessage(f"Sorry, I had trouble searching your calendar: {events_response['error']}"))
            state['cancellation_candidates'] = []
        else:
            state['cancellation_candidates'] = events_response.get('items', [])
        
        return state

    async def _list_found_events(self, state: AgentState) -> AgentState:
        """New node to format and list events found on a specific day."""
        logger.debug(f"[{state['session_id']}] Node: _list_found_events")
        events = state.get('cancellation_candidates', [])
        
        if not events:
            response_message = "I looked at that day and couldn't find any scheduled events."
        else:
            event_list_str = []
            for event in events:
                summary = event.get('summary', 'No Title')
                start_time_str = event.get('start', {}).get('dateTime')
                start_time_obj = parser.parse(start_time_str)
                formatted_time = start_time_obj.strftime('%I:%M %p')
                event_list_str.append(f"- {formatted_time}: {summary}")
            
            response_message = "I found the following events for you:\n" + "\n".join(event_list_str)

        state['messages'].append(AIMessage(content=response_message))
        return state
    


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
        
    async def process_message(self, message: str, session_id: str, context: Dict, calendar_service: CalendarService) -> Dict[str, Any]:
        logger.info(f"Processing message for session_id: {session_id}")
        if session_id not in self.sessions:
            self.sessions[session_id] = self.initial_state.copy()
            self.sessions[session_id]['session_id'] = session_id
        
        state = self.sessions[session_id]
        state['messages'].append(HumanMessage(content=message))
        if context:
            state['context'].update(context)

        graph_config = {"configurable": {"calendar_service": calendar_service}}
        result_state = await self.graph.ainvoke(state, config=graph_config)
        
        self.sessions[session_id] = result_state
        logger.info(f"Finished processing. Final intent: '{result_state['intent']}'")
        return {
            "message": result_state['messages'][-1].content if result_state['messages'] else "How can I help you?",
            "context": result_state['context'], "intent": result_state['intent']
        }

    async def _understand_intent(self, state: AgentState) -> AgentState:
        """Node to understand the user's intent from the latest message."""
        logger.debug(f"[{state['session_id']}] Node: _understand_intent")
        latest_message = state['messages'][-1].content
        prompt = f"""
        Analyze the user's message for a booking assistant.
        Message: "{latest_message}"

        Classify the intent as one of:
        - "find_event": The user is asking about events they have on a certain day (e.g., "What do I have on Friday?", "Any meetings today?").
        - "book_appointment": User wants to schedule a new appointment (e.g., "Book a meeting", "I need an appointment").
        - "check_availability": User is asking about available times without committing (e.g., "Are you free tomorrow?", "What times are open?").
        - "cancel_appointment": User wants to cancel an existing event (e.g., "Cancel my 3pm meeting").
        - "reschedule_appointment": User wants to move an existing event to a new time (e.g., "Move my meeting to 4pm").
        - "general_inquiry": For questions that don't fit other categories, or if the intent is unclear.

        Respond with JSON: {{"intent": "classified_intent"}}
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

    async def _check_availability(self, state: AgentState, config: dict) -> AgentState:
        calendar_service: CalendarService = config["configurable"]["calendar_service"]
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

    async def _confirm_booking(self, state: AgentState, config: dict) -> AgentState:
        calendar_service: CalendarService = config["configurable"]["calendar_service"]
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
    
    async def _check_specific_slot(self, state: AgentState, config: dict) -> AgentState:
        calendar_service: CalendarService = config["configurable"]["calendar_service"]
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