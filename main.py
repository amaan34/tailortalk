from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

from agent import TailorTalkAgent
from models import ChatMessage

# --- Logging Configuration ---
# Configure logging to output to console with a specific format and level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- Environment Variable Loading ---
load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    logger.critical("FATAL: OPENAI_API_KEY environment variable is not set.")
    raise RuntimeError("Missing OPENAI_API_KEY. Please set it in your environment or a .env file.")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="TailorTalk API",
    description="A conversational AI booking agent backend.",
    version="1.0.0"
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Logging Middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to log incoming requests and their processing time."""
    start_time = time.time()
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"Response status: {response.status_code} | Process time: {process_time:.4f}s")
    return response

# --- Agent Initialization ---
try:
    agent = TailorTalkAgent()
    logger.info("TailorTalk Agent initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize TailorTalk Agent: {e}", exc_info=True)
    raise

# --- API Endpoints ---

@app.post("/chat", response_model=ChatMessage)
async def chat(message: ChatMessage):
    """
    This is the primary endpoint for interacting with the agent.
    It processes a chat message and returns the agent's response.
    """
    logger.info(f"Received chat message from session: {message.session_id}")
    try:
        response_data = await agent.process_message(
            message.content,
            message.session_id,
            message.context
        )
        return ChatMessage(
            content=response_data["message"],
            session_id=message.session_id,
            context=response_data.get("context", {}),
            timestamp=datetime.now(),
            sender="agent"
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred in the chat endpoint: {e}", exc_info=True)
        # Raising HTTPException will forward a clean error to the client
        raise HTTPException(
            status_code=500, 
            detail="An internal server error occurred. Please try again later."
        )

@app.get("/health", summary="Health Check")
async def health_check():
    """Provides a simple health check endpoint to verify the service is running."""
    logger.info("Health check endpoint was called.")
    return {"status": "healthy", "service": "TailorTalk API", "timestamp": datetime.now()}


if __name__ == "__main__":
    logger.info("Starting TailorTalk FastAPI server.")
    uvicorn.run(app, host="0.0.0.0", port=8000)