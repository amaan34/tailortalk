from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import asyncio
import logging
import json

# Set up a logger for this service
logger = logging.getLogger(__name__)

class CalendarService:
    """
    A service class to handle all interactions with the Google Calendar API.
    This class is now instantiated with a specific user's credentials.
    """
    def __init__(self, user_credentials: dict):
        """
        Initializes the service with a user's token dictionary.
        """
        try:
            # Create credentials directly from the user's token dictionary
            self.credentials = Credentials.from_authorized_user_info(user_credentials, scopes=['https://www.googleapis.com/auth/calendar'])
            self.service = build('calendar', 'v3', credentials=self.credentials)
            logger.info("CalendarService instantiated for a user.")
        except Exception as e:
            logger.error(f"Failed to create calendar service with user credentials: {e}")
            raise

    async def _get_service(self) -> Resource:
        """Ensures the service is authenticated and returns the service object."""
        # In this implementation, the service is created in the constructor, so we just return it.
        # A more complex implementation might refresh the token here if it's expired.
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
                'start': {'dateTime': start_time, 'timeZone': 'Asia/Kolkata'},
                'end': {'dateTime': end_time, 'timeZone': 'Asia/Kolkata'},
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

    async def search_events(self, start_time: str, end_time: str, query: Optional[str] = None) -> Dict:
        """Asynchronously searches for events within a given time range."""
        logger.info(f"Searching for events from {start_time} to {end_time} with query: '{query}'")
        try:
            service = await self._get_service()

            # [MODIFICATION] Build params dict conditionally to avoid sending `q=None`
            params = {
                'calendarId': 'primary',
                'timeMin': start_time,
                'timeMax': end_time,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            if query:
                params['q'] = query

            def _blocking_call():
                return service.events().list(**params).execute()

            events_result = await asyncio.to_thread(_blocking_call)
            logger.info(f"Found {len(events_result.get('items', []))} events.")
            return events_result
        except Exception as e:
            logger.error(f"An error occurred while searching events: {e}", exc_info=True)
            return {"error": f"Failed to search for events in Calendar API: {e}"}

    async def delete_event(self, event_id: str) -> Dict:
        """Asynchronously deletes a calendar event by its ID."""
        logger.info(f"Attempting to delete event with ID: {event_id}")
        try:
            service = await self._get_service()

            def _blocking_call():
                service.events().delete(calendarId='primary', eventId=event_id).execute()
                return {"success": True, "event_id": event_id}

            result = await asyncio.to_thread(_blocking_call)
            logger.info(f"Successfully deleted event with ID: {event_id}")
            return result
        except Exception as e:
            logger.error(f"An error occurred while deleting the event: {e}", exc_info=True)
            return {"error": f"Failed to delete event in Calendar API: {e}"}

    async def update_event(self, event_id: str, body: Dict) -> Dict:
        """Asynchronously updates an existing calendar event."""
        logger.info(f"Attempting to update event with ID: {event_id}")
        try:
            service = await self._get_service()

            def _blocking_call():
                return service.events().update(
                    calendarId='primary', eventId=event_id, body=body
                ).execute()

            updated_event = await asyncio.to_thread(_blocking_call)
            logger.info(f"Successfully updated event with ID: {event_id}")
            return updated_event
        except Exception as e:
            logger.error(f"An error occurred while updating the event: {e}", exc_info=True)
            return {"error": f"Failed to update event in Calendar API: {e}"}