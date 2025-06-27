from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    """Chat message model"""
    content: str = Field(..., description="Message content")
    session_id: str = Field(..., description="Session identifier")
    context: Dict[str, Any] = Field(default_factory=dict, description="Message context")
    timestamp: datetime = Field(default_factory=datetime.now, description="Message timestamp")
    sender: str = Field(default="user", description="Message sender (user/agent)")

class BookingRequest(BaseModel):
    """Appointment booking request"""
    title: str = Field(..., description="Appointment title")
    start_time: str = Field(..., description="Start time (ISO format)")
    end_time: str = Field(..., description="End time (ISO format)")
    description: Optional[str] = Field(None, description="Appointment description")
    attendees: Optional[List[str]] = Field(default_factory=list, description="Attendee emails")
    session_id: Optional[str] = Field(None, description="Chat session ID")

class BookingResponse(BaseModel):
    """Appointment booking response"""
    success: bool = Field(..., description="Booking success status")
    booking_id: Optional[str] = Field(None, description="Created booking ID")
    message: str = Field(..., description="Response message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional booking details")

class AvailabilitySlot(BaseModel):
    """Available time slot"""
    start: str = Field(..., description="Slot start time (ISO format)")
    end: str = Field(..., description="Slot end time (ISO format)")
    title: str = Field(..., description="Slot description")
    duration_minutes: int = Field(default=30, description="Slot duration in minutes")

class AgentIntent(BaseModel):
    """Detected user intent"""
    intent: str = Field(..., description="Primary intent category")
    confidence: float = Field(..., description="Confidence score (0-1)")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    requires_clarification: bool = Field(default=False, description="Whether clarification is needed")

class ConversationState(BaseModel):
    """Conversation state tracking"""
    session_id: str = Field(..., description="Session identifier")
    current_intent: Optional[str] = Field(None, description="Current conversation intent")
    extracted_info: Dict[str, Any] = Field(default_factory=dict, description="Extracted information")
    conversation_stage: str = Field(default="greeting", description="Current conversation stage")
    suggested_slots: List[AvailabilitySlot] = Field(default_factory=list, description="Suggested time slots")
    pending_confirmation: Optional[BookingRequest] = Field(None, description="Booking awaiting confirmation")