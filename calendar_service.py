from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os

class CalendarService:
    """Google Calendar integration service"""
    
    def __init__(self):
        self.service = None
        self.credentials = None
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        
        # --- [MODIFICATION] Mock mode is now disabled ---
        self.mock_mode = False
        
        if not self.mock_mode:
            self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API using a local flow."""
        creds = None
        
        # The file token.json stores the user's access and refresh tokens.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.scopes)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # --- [MODIFICATION] Use InstalledAppFlow for desktop apps ---
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.scopes)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
        self.credentials = creds
        self.service = build('calendar', 'v3', credentials=creds)
    
    async def get_availability(self, start_time: str, end_time: str) -> List[Dict]:
        """Get available time slots between start and end time"""
        if self.mock_mode:
            return self._get_mock_availability(start_time, end_time)
        
        try:
            body = {
                "timeMin": start_time,
                "timeMax": end_time,
                "items": [{"id": "primary"}]
            }
            # --- [MODIFICATION] Return the raw API response ---
            freebusy_response = self.service.freebusy().query(body=body).execute()
            return freebusy_response
            
        except Exception as e:
            print(f"Error fetching availability: {e}")
            return {"error": str(e)}

    # --- [MODIFICATION] create_event now returns the full event object ---
    async def create_event(self, title: str, start_time: str, end_time: str, 
                           description: str = "", attendees: List[str] = None) -> Dict:
        """Create a calendar event and return the raw API response."""
        if self.mock_mode:
            # This part will not be used, but is kept for completeness
            return self._create_mock_event(title, start_time, end_time, description, attendees)
        
        try:
            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_time,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': 'UTC',
                },
            }
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            # Execute the request and return the entire created event object
            created_event = self.service.events().insert(calendarId='primary', body=event).execute()
            return created_event
            
        except Exception as e:
            print(f"Error creating event: {e}")
            return {"error": str(e)}

    # Mock functions remain for fallback or future use but won't be called now
    def _get_mock_availability(self, start_time: str, end_time: str) -> List[Dict]:
        # ...
        pass
    def _create_mock_event(self, title: str, start_time: str, end_time: str, 
                           description: str = "", attendees: List[str] = None) -> Dict:
        # ...
        pass