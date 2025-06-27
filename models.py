from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    """Model for a single chat message in a conversation."""
    content: str = Field(..., description="The text content of the message.")
    session_id: str = Field(..., description="A unique identifier for the conversation session.")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context to be passed between client and server.")
    timestamp: datetime = Field(default_factory=datetime.now, description="The timestamp of when the message was created.")
    sender: str = Field(default="user", description="The sender of the message, either 'user' or 'agent'.")

class BookingRequest(BaseModel):
    """Model for an appointment booking request."""
    title: str = Field(..., description="The title or summary of the appointment.")
    start_time: str = Field(..., description="The start time of the appointment in ISO 8601 format.")
    end_time: str = Field(..., description="The end time of the appointment in ISO 8601 format.")
    description: Optional[str] = Field(None, description="A detailed description of the appointment.")
    attendees: Optional[List[EmailStr]] = Field(default_factory=list, description="A list of attendee email addresses.")
    session_id: Optional[str] = Field(None, description="The chat session ID associated with this booking.")

class BookingResponse(BaseModel):
    """Model for the response after a booking attempt."""
    success: bool = Field(..., description="Indicates whether the booking was successfully created.")
    booking_id: Optional[str] = Field(None, description="The unique ID of the created calendar event.")
    message: str = Field(..., description="A user-friendly message describing the outcome.")
    details: Optional[Dict[str, Any]] = Field(None, description="The full details of the created event from the calendar API.")

class AvailabilitySlot(BaseModel):
    """Model representing a single available time slot."""
    start: str = Field(..., description="The start time of the slot in ISO 8601 format.")
    end: str = Field(..., description="The end time of the slot in ISO 8601 format.")
    title: str = Field(default="Available Slot", description="A descriptive title for the slot.")
    duration_minutes: int = Field(default=30, description="The duration of the slot in minutes.")

class AgentIntent(BaseModel):
    """Model for capturing the detected user intent."""
    intent: str = Field(..., description="The primary category of the user's intent (e.g., 'book_appointment').")
    confidence: float = Field(..., description="The confidence score of the intent detection, from 0 to 1.")
    entities: Dict[str, Any] = Field(default_factory=dict, description="A dictionary of extracted entities, like dates or names.")
    requires_clarification: bool = Field(default=False, description="True if the agent needs more information to proceed.")

class ConversationState(BaseModel):
    """Model for tracking the state of a conversation session."""
    session_id: str = Field(..., description="The unique identifier for the session.")
    current_intent: Optional[str] = Field(None, description="The currently active intent for the conversation.")
    extracted_info: Dict[str, Any] = Field(default_factory=dict, description="Information extracted from the user's messages.")
    conversation_stage: str = Field(default="greeting", description="The current stage of the conversation (e.g., 'clarifying', 'confirming').")
    suggested_slots: List[AvailabilitySlot] = Field(default_factory=list, description="A list of time slots suggested to the user.")
    pending_confirmation: Optional[BookingRequest] = Field(None, description="A booking request that is awaiting user confirmation.")