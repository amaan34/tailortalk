from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import asyncio
import logging

# Set up a logger for this service
logger = logging.getLogger(__name__)

class CalendarService:
    """
    A service class to handle all interactions with the Google Calendar API.
    This class is now fully async and uses asyncio.to_thread for blocking calls.
    """
    
    def __init__(self, scopes: List[str] = ['https://www.googleapis.com/auth/calendar']):
        self.service: Optional[Resource] = None
        self.credentials: Optional[Credentials] = None
        self.scopes = scopes
        self.token_file = 'token.json'
        self.creds_file = 'credentials.json'

    async def _authenticate(self):
        """
        Asynchronously authenticates with the Google Calendar API.
        Handles token loading, refreshing, and new user authorization.
        """
        logger.info("Attempting to authenticate with Google Calendar API.")
        creds = None
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
                logger.info("Loaded credentials from token.json.")
            except Exception as e:
                logger.error(f"Failed to load credentials from token.json: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Credentials have expired. Refreshing token...")
                try:
                    creds.refresh(Request())
                    logger.info("Token refreshed successfully.")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}. Re-authentication will be required.")
                    creds = None # Force re-authentication
            else:
                logger.info("No valid credentials found. Starting local server for new authorization.")
                if not os.path.exists(self.creds_file):
                    logger.critical(f"FATAL: credentials.json not found. Cannot authenticate.")
                    raise FileNotFoundError(f"Missing required credentials file: {self.creds_file}")
                
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_file, self.scopes)
                # Running the local server in a separate thread to avoid blocking asyncio event loop
                creds = await asyncio.to_thread(flow.run_local_server, port=0)
            
            # Save the new or refreshed credentials
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
            logger.info(f"Credentials saved to {self.token_file}.")
            
        self.credentials = creds
        self.service = build('calendar', 'v3', credentials=self.credentials)
        logger.info("Google Calendar service built successfully.")

    async def _get_service(self) -> Resource:
        """Ensures the service is authenticated and returns the service object."""
        if not self.service:
            await self._authenticate()
        return self.service

    async def get_availability(self, start_time: str, end_time: str) -> Dict:
        """
        Asynchronously gets available time slots between a start and end time.
        """
        logger.info(f"Fetching availability from {start_time} to {end_time}.")
        try:
            service = await self._get_service()
            body = {
                "timeMin": start_time,
                "timeMax": end_time,
                "items": [{"id": "primary"}] # Check against the primary calendar
            }
            
            def _blocking_call():
                return service.freebusy().query(body=body).execute()

            freebusy_response = await asyncio.to_thread(_blocking_call)
            logger.info("Successfully fetched free/busy information.")
            return freebusy_response
            
        except Exception as e:
            logger.error(f"An error occurred while fetching availability: {e}", exc_info=True)
            return {"error": f"Failed to communicate with Calendar API: {e}"}

    async def create_event(self, title: str, start_time: str, end_time: str,  
                             description: str = "", attendees: Optional[List[str]] = None) -> Dict:
        """
        Asynchronously creates a calendar event and returns the API response.
        """
        logger.info(f"Creating calendar event: '{title}' from {start_time} to {end_time}.")
        try:
            service = await self._get_service()
            event_details = {
                'summary': title,
                'description': description,
                # [MODIFICATION] Remove the explicit 'timeZone' key.
                # The timezone info is now included in the start_time and end_time ISO strings.
                'start': {'dateTime': start_time},
                'end': {'dateTime': end_time},
            }
            if attendees:
                event_details['attendees'] = [{'email': email} for email in attendees]

            def _blocking_call():
                return service.events().insert(calendarId='primary', body=event_details).execute()

            created_event = await asyncio.to_thread(_blocking_call)
            logger.info(f"Successfully created event with ID: {created_event.get('id')}")
            return created_event
            
        except Exception as e:
            logger.error(f"An error occurred while creating the event: {e}", exc_info=True)
            return {"error": f"Failed to create event in Calendar API: {e}"}