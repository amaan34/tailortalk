from fastapi import FastAPI, HTTPException, Request, Query, Header, status, Depends
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
from starlette.middleware.sessions import SessionMiddleware

from agent import TailorTalkAgent
from models import ChatMessage
from database import init_db, get_db, UserToken
from security import encrypt_token, decrypt_token
from calendar_service import CalendarService

# --- Logging and App Initialization ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = FastAPI(title="TailorTalk API", docs_url="/docs") # Explicitly set docs_url
load_dotenv()

# --- Middleware Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("Missing SECRET_KEY for SessionMiddleware")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Agent and DB Initialization ---
try:
    agent = TailorTalkAgent()
    logger.info("TailorTalk Agent initialized successfully.")
    init_db()
    logger.info("Database initialized.")
except Exception as e:
    logger.critical(f"Failed to initialize TailorTalk Agent or DB: {e}", exc_info=True)
    raise

LOCAL_TIMEZONE = pytz.timezone("Asia/Kolkata")
CLIENT_CONFIG = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
SCOPES = ['https://www.googleapis.com/auth/calendar']

# --- Authentication Endpoints (Corrected) ---

@app.get("/login", tags=["Authentication"])
def login(request: Request):
    """Initiates the Google OAuth2 login flow."""
    # [FIX] Construct the redirect URI manually for robustness
    redirect_uri = f"{request.base_url}callback"
    
    flow = Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    request.session['state'] = state
    logger.info(f"Redirecting user to Google for authentication. State: {state}")
    return RedirectResponse(authorization_url)


@app.get("/callback", tags=["Authentication"])
async def callback(request: Request, db: Session = Depends(get_db)):
    """Handles the redirect from Google after user authentication."""
    state = request.session.get('state')
    if not state:
        raise HTTPException(status_code=400, detail="Session state missing.")

    # [FIX] Construct the redirect URI manually to match the /login route
    redirect_uri = f"{request.base_url}callback"

    flow = Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri
    )
    
    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception as e:
        logger.error(f"Error fetching token from Google: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch token: {e}")

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

    # [FIX] Use the environment variable for the Streamlit app URL
    streamlit_url = os.getenv("STREAMLIT_APP_URL")
    if not streamlit_url:
        logger.error("STREAMLIT_APP_URL environment variable not set!")
        raise HTTPException(status_code=500, detail="Application is not configured correctly.")
        
    final_redirect_url = f"{streamlit_url}?session_id={session_id}"
    logger.info(f"Successfully authenticated user. Redirecting to: {final_redirect_url}")
    return RedirectResponse(final_redirect_url)


# --- Dependency for getting the Calendar Service ---
async def get_calendar_service(x_session_id: str = Header(...), db: Session = Depends(get_db)) -> CalendarService:
    if not x_session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session ID missing")
    db_token = db.query(UserToken).filter(UserToken.session_id == x_session_id).first()
    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session ID")
    user_creds = decrypt_token(db_token.encrypted_token)
    return CalendarService(user_credentials=user_creds)

# --- Modified API Endpoints ---
@app.post("/chat", tags=["Agent"])
async def chat(message: ChatMessage, calendar_service: CalendarService = Depends(get_calendar_service)):
    response_data = await agent.process_message(
        message=message.content,
        session_id=message.session_id,
        context=message.context,
        calendar_service=calendar_service
    )
    return ChatMessage(
        content=response_data["message"], session_id=message.session_id,
        context=response_data.get("context", {}), sender="agent"
    )

@app.get("/events", tags=["Calendar"])
async def get_events(
    calendar_service: CalendarService = Depends(get_calendar_service),
    start_date: str = Query(None),
    end_date: str = Query(None)
):
    now_aware = datetime.now(LOCAL_TIMEZONE)
    effective_start_date = start_date or now_aware.isoformat()
    effective_end_date = end_date or (now_aware + timedelta(days=14)).isoformat()
    
    logger.info(f"Fetching events from {effective_start_date} to {effective_end_date}")
    events_data = await calendar_service.search_events(effective_start_date, effective_end_date)
    if "error" in events_data:
        raise HTTPException(status_code=502, detail=f"Error from Calendar API: {events_data['error']}")
    return events_data.get("items", [])

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)