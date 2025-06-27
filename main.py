from fastapi import FastAPI, HTTPException, Request, Query, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn
import os
import logging
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import uuid
import json
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from database import init_db, get_db, UserToken
from security import encrypt_token, decrypt_token
from calendar_service import CalendarService
from agent import TailorTalkAgent
from models import ChatMessage
from starlette.middleware.sessions import SessionMiddleware

# Initialize the database on startup
init_db()

# --- Google OAuth2 Flow Setup ---
# This uses the credentials.json file content from your environment variable
CLIENT_CONFIG = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
SCOPES = ['https://www.googleapis.com/auth/calendar']


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
    init_db()
    logger.info("Database initialized.")
except Exception as e:
    logger.critical(f"Failed to initialize TailorTalk Agent: {e}", exc_info=True)
    raise

# --- Timezone Configuration ---
LOCAL_TIMEZONE = pytz.timezone("Asia/Kolkata")


# --- New Endpoints for Authentication ---

@app.get("/login")
def login(request: Request):
    """Initiates the Google OAuth2 login flow."""
    flow = Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=str(request.url_for('callback'))
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    request.session['state'] = state
    return RedirectResponse(authorization_url)

@app.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """Handles the redirect from Google after user authentication."""
    state = request.session['state']
    flow = Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=SCOPES,
        state=state,
        redirect_uri=str(request.url_for('callback'))
    )
    flow.fetch_token(authorization_response=str(request.url))

    credentials = flow.credentials
    token = {
        'token': credentials.token, 'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
        'client_secret': credentials.client_secret, 'scopes': credentials.scopes
    }

    encrypted_token = encrypt_token(token)
    session_id = str(uuid.uuid4())
    db_token = UserToken(session_id=session_id, encrypted_token=encrypted_token)
    db.add(db_token)
    db.commit()

    # Get the Streamlit app's URL from an environment variable if available
    streamlit_url = os.getenv("STREAMLIT_APP_URL", "http://localhost:8501")
    return RedirectResponse(f"{streamlit_url}?session_id={session_id}")


# --- Dependency for getting the Calendar Service ---

async def get_calendar_service(x_session_id: str = Header(), db: Session = Depends(get_db)) -> CalendarService:
    """Dependency to get a user-specific CalendarService instance."""
    if not x_session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session ID missing")
    
    db_token = db.query(UserToken).filter(UserToken.session_id == x_session_id).first()
    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session ID")
        
    user_creds = decrypt_token(db_token.encrypted_token)
    return CalendarService(user_credentials=user_creds)


# --- API Endpoints ---

@app.post("/chat", response_model=ChatMessage)
async def chat(message: ChatMessage,
               calendar_service: CalendarService = Depends(get_calendar_service)):
    """
    This is the primary endpoint for interacting with the agent.
    It processes a chat message and returns the agent's response.
    """
    logger.info(f"Received chat message from session: {message.session_id}")
    try:
        response_data = await agent.process_message(
            message.content,
            message.session_id,
            message.context,
            calendar_service
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


@app.get("/events", summary="Get Upcoming Calendar Events")
async def get_events(
    start_date: str = Query(None, description="Start date in ISO format"),
    end_date: str = Query(None, description="End date in ISO format"),
    calendar_service: CalendarService = Depends(get_calendar_service)
):
    """
    Fetches upcoming events from the user's primary calendar.
    """
    try:
        # [FIX] Use timezone-aware datetime objects
        now_aware = datetime.now(LOCAL_TIMEZONE)
        if not start_date:
            start_date = now_aware.isoformat()
        if not end_date:
            end_date = (now_aware + timedelta(days=14)).isoformat()

        logger.info(f"Fetching events from {start_date} to {end_date}")
        events_data = await agent.calendar_service.search_events(start_date, end_date)

        if "error" in events_data:
            # Log the specific error from the calendar service before raising a generic one
            logger.error(f"Calendar service error: {events_data['error']}")
            raise HTTPException(status_code=502, detail=f"Error from Calendar API: {events_data['error']}")

        return events_data.get("items", [])
    except HTTPException as http_exc:
        # Re-raise HTTPException to ensure FastAPI handles it correctly
        raise http_exc
    except Exception as e:
        logger.error(f"An unexpected error occurred in /events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred while fetching events.")


if __name__ == "__main__":
    logger.info("Starting TailorTalk FastAPI server.")
    uvicorn.run(app, host="0.0.0.0", port=8000)