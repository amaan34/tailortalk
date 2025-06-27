import pytest
import asyncio
from agent import TailorTalkAgent
from models import BookingRequest

@pytest.mark.asyncio
async def test_process_message():
    agent = TailorTalkAgent()
    response = await agent.process_message("I want to book an appointment tomorrow at 3pm", session_id="test1")
    assert isinstance(response, dict)
    assert "message" in response
    assert "intent" in response

@pytest.mark.asyncio
async def test_book_appointment(monkeypatch):
    agent = TailorTalkAgent()
    booking = BookingRequest(
        title="Test Meeting",
        start_time="2024-06-01T15:00:00",
        end_time="2024-06-01T16:00:00",
        description="Test Description",
        attendees=["test@example.com"]
    )
    # Mock calendar_service.create_event
    async def mock_create_event(*args, **kwargs):
        return {"id": "123", "status": "confirmed"}
    agent.calendar_service.create_event = mock_create_event
    response = await agent.book_appointment(booking)
    assert response.success
    assert response.booking_id == "123"

@pytest.mark.asyncio
async def test_get_availability(monkeypatch):
    agent = TailorTalkAgent()
    # Mock calendar_service.get_availability
    async def mock_get_availability(start, end):
        return [{"start": start, "end": end}]
    agent.calendar_service.get_availability = mock_get_availability
    result = await agent.get_availability("2024-06-01T09:00:00", "2024-06-01T17:00:00")
    assert isinstance(result, list)
    assert "start" in result[0] and "end" in result[0] 