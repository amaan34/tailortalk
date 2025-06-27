from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import os

from agent import TailorTalkAgent
from models import ChatMessage, BookingRequest, BookingResponse

load_dotenv()  # Load environment variables from .env if present

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Missing OPENAI_API_KEY. Please set it in your environment or in a .env file.")

app = FastAPI(title="TailorTalk API", description="Conversational AI Booking Agent")

# CORS middleware for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the agent
agent = TailorTalkAgent()

@app.post("/chat", response_model=ChatMessage)
async def chat(message: ChatMessage):
    """Process a chat message and return agent response"""
    try:
        response = await agent.process_message(
            message.content, 
            message.session_id,
            message.context
        )
        return ChatMessage(
            content=response["message"],
            session_id=message.session_id,
            context=response.get("context", {}),
            timestamp=datetime.now(),
            sender="agent"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/book", response_model=BookingResponse)
async def book_appointment(booking: BookingRequest):
    """Book an appointment"""
    try:
        result = await agent.book_appointment(booking)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/availability")
async def get_availability(start_date: str, end_date: str):
    """Get available time slots"""
    try:
        availability = await agent.get_availability(start_date, end_date)
        return {"availability": availability}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "TailorTalk"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)