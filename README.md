from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
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
        
        # For demo purposes, we'll use mock data
        # In production, you'd set up proper OAuth flow
        self.mock_mode = True
        
        if not self.mock_mode:
            self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None
        
        # Check if token.json exists (stored credentials)
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.scopes)
        
        # If there are no valid credentials, request authorization
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = Flow.from_client_secrets_file(
                    'credentials.json', self.scopes)
                flow.redirect_uri = 'http://localhost:8080/callback'
                
                # This would typically be handled by a web flow
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(f'Please go to this URL: {auth_url}')
                
                # In a real app, you'd handle the callback
                # For now, we'll use mock data
                
        self.credentials = creds
        if creds:
            self.service = build('calendar', 'v3', credentials=creds)
    
    async def get_availability(self, start_time: str, end_time: str) -> List[Dict]:
        """Get available time slots between start and end time"""
        if self.mock_mode:
            return self._get_mock_availability(start_time, end_time)
        
        try:
            # Query calendar for busy times
            body = {
                "timeMin": start_time,
                "timeMax": end_time,
                "items": [{"id": "primary"}]
            }
            
            freebusy = self.service.freebusy().query(body=body).execute()
            busy_times = freebusy['calendars']['primary']['busy']
            
            # Generate available slots (assuming 30-minute slots)
            available_slots = self._generate_available_slots(
                start_time, end_time, busy_times
            )
            
            return available_slots
            
        except Exception as e:
            print(f"Error fetching availability: {e}")
            return self._get_mock_availability(start_time, end_time)
    
    def _get_mock_availability(self, start_time: str, end_time: str) -> List[Dict]:
        """Generate mock availability data for demo"""
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        available_slots = []
        current_time = start_dt
        
        # Generate 30-minute slots
        while current_time < end_dt:
            slot_end = current_time + timedelta(minutes=30)
            
            # Skip lunch time (12-1 PM) and some random busy slots
            if not (current_time.hour == 12 or 
                   (current_time.hour == 14 and current_time.minute == 30) or
                   (current_time.hour == 10 and current_time.minute == 0)):
                
                available_slots.append({
                    "start": current_time.isoformat(),
                    "end": slot_end.isoformat(),
                    "title": f"Available - {current_time.strftime('%I:%M %p')}"
                })
            
            current_time += timedelta(minutes=30)
        
        return available_slots[:10]  # Return first 10 slots
    
    def _generate_available_slots(self, start_time: str, end_time: str, busy_times: List[Dict]) -> List[Dict]:
        """Generate available slots excluding busy times"""
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        available_slots = []
        current_time = start_dt
        
        # Convert busy times to datetime objects
        busy_periods = []
        for busy in busy_times:
            busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
            busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
            busy_periods.append((busy_start, busy_end))
        
        # Generate slots avoiding busy periods
        while current_time < end_dt:
            slot_end = current_time + timedelta(minutes=30)
            
            # Check if this slot conflicts with any busy period
            is_available = True
            for busy_start, busy_end in busy_periods:
                if (current_time < busy_end and slot_end > busy_start):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append({
                    "start": current_time.isoformat(),
                    "end": slot_end.isoformat(),
                    "title": f"Available - {current_time.strftime('%I:%M %p')}"
                })
            
            current_time += timedelta(minutes=30)
        
        return available_slots
    
    async def create_event(self, title: str, start_time: str, end_time: str, 
                          description: str = "", attendees: List[str] = None) -> Dict:
        """Create a calendar event"""
        if self.mock_mode:
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
            
            event = self.service.events().insert(calendarId='primary', body=event).execute()
            return {
                'id': event['id'],
                'htmlLink': event['htmlLink'],
                'status': 'confirmed'
            }
            
        except Exception as e:
            print(f"Error creating event: {e}")
            return self._create_mock_event(title, start_time, end_time, description, attendees)
    
    def _create_mock_event(self, title: str, start_time: str, end_time: str, 
                          description: str = "", attendees: List[str] = None) -> Dict:
        """Create a mock event for demo purposes"""
        import uuid
        
        return {
            'id': str(uuid.uuid4()),
            'htmlLink': f'https://calendar.google.com/calendar/event?eid={uuid.uuid4()}',
            'status': 'confirmed',
            'summary': title,
            'start': start_time,
            'end': end_time,
            'description': description,
            'attendees': attendees or []
        }
    
    async def get_events(self, start_time: str, end_time: str) -> List[Dict]:
        """Get events in a time range"""
        if self.mock_mode:
            return [
                {
                    'id': '1',
                    'summary': 'Team Meeting',
                    'start': '2024-01-15T14:00:00Z',
                    'end': '2024-01-15T15:00:00Z'
                },
                {
                    'id': '2', 
                    'summary': 'Client Call',
                    'start': '2024-01-15T16:00:00Z',
                    'end': '2024-01-15T17:00:00Z'
                }
            ]
        
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            return events
            
        except Exception as e:
            print(f"Error fetching events: {e}")
            return []