from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import dateparser
import pytz  

SCOPES = ['https://www.googleapis.com/auth/calendar.events',
          'https://www.googleapis.com/auth/calendar.readonly']

def create_event(summary, start_time, attendees=None):
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    # Convert start_time (ISO string) to IST
    dt_utc = datetime.fromisoformat(start_time)
    ist = pytz.timezone('Asia/Kolkata')
    dt_ist = dt_utc.astimezone(ist)
    end_ist = dt_ist + timedelta(hours=1)

    event = {
        'summary': summary,
        'start': {'dateTime': dt_ist.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_ist.isoformat(), 'timeZone': 'Asia/Kolkata'}
    }
    if attendees:
        event['attendees'] = [{'email': email} for email in attendees]

    created_event = service.events().insert(calendarId='primary', body=event, sendUpdates="all" if attendees else "none").execute()
    event_id = created_event.get('id')
    event_start = created_event['start'].get('dateTime', created_event['start'].get('date'))
    event_title = created_event.get('summary', summary)

    # Format date in readable way
    dt_obj = datetime.fromisoformat(event_start)
    dt_obj_ist = dt_obj.astimezone(ist)
    readable_time = dt_obj_ist.strftime("%d %B %Y, %I:%M %p IST")

    # Return structured data for Flask
    return {
        'status': 'success',
        'message': 'Event created successfully!',
        'data': {
            'title': event_title,
            'date': readable_time,
            'event_id': event_id,
            'attendees': attendees if attendees else []
        }
    }


def create_event_nlp(summary, natural_date):
    dt = dateparser.parse(natural_date)
    if not dt:
        return {
            'status': 'error',
            'message': 'Could not parse the date/time.',
            'data': None
        }
    return create_event(summary, dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"))


def list_upcoming_events(max_results=5):
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    now = datetime.utcnow().isoformat() + 'Z' 
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    if not events:
        return {
            'status': 'success',
            'message': 'No upcoming events found.',
            'data': []
        }

    formatted_events = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'No Title')
        event_id = event.get('id', '-')
        
        # Format date properly
        try:
            if 'T' in start:
                date_obj = datetime.fromisoformat(start.replace('Z', '+00:00'))
            else:
                date_obj = datetime.fromisoformat(start)
            formatted_date = date_obj.strftime("%B %d, %Y at %I:%M %p")
        except:
            formatted_date = start
            
        formatted_events.append({
            'title': summary,
            'date': formatted_date,
            'event_id': event_id
        })

    return {
        'status': 'success',
        'message': f'Found {len(formatted_events)} upcoming events.',
        'data': formatted_events
    }

def delete_event(event_id):
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return {
            'status': 'success',
            'message': 'Event deleted successfully!',
            'data': {'event_id': event_id}
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Failed to delete event: {str(e)}',
            'data': None
        }

def delete_all_events():
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    now = datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    if not events:
        return {
            'status': 'success',
            'message': 'No upcoming events to delete.',
            'data': {'deleted_count': 0}
        }
    
    deleted_ids = []
    for event in events:
        try:
            service.events().delete(calendarId='primary', eventId=event['id']).execute()
            deleted_ids.append(event['id'])
        except Exception:
            continue
    
    return {
        'status': 'success',
        'message': f'Deleted {len(deleted_ids)} upcoming events.',
        'data': {'deleted_count': len(deleted_ids), 'deleted_ids': deleted_ids}
    }

# HOLIDAYS FUNCTIONALITY

def get_all_holiday_calendars():
    """Get all holiday-related calendars (Indian + International)"""
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    calendar_list = service.calendarList().list().execute().get('items', [])
    holiday_calendars = {}

    for calendar in calendar_list:
        name = calendar.get('summary', '').lower()
        cal_id = calendar.get('id')

        if 'holiday' in name:
            if 'india' in name:
                holiday_calendars['India'] = cal_id
            else:
                holiday_calendars[calendar.get('summary', 'Other')] = cal_id

    return holiday_calendars

def list_remaining_events_this_month_from_calendar(calendar_id):
    """List events from a given calendar for the remaining days of the current month"""
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    now = datetime.now(pytz.UTC)
    start_time = now
    if now.month == 12:
        end_of_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        end_of_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start_time.isoformat(),
        timeMax=end_of_month.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    return events_result.get('items', [])

def list_holidays():
    """Display upcoming holidays from Indian + International calendars for the rest of the current month"""
    calendars = get_all_holiday_calendars()
    if not calendars:
        return {
            'status': 'error',
            'message': 'No holiday calendars found. Make sure you are subscribed to them.',
            'data': None
        }

    all_holidays = {}
    for region, cal_id in calendars.items():
        events = list_remaining_events_this_month_from_calendar(cal_id)
        if not events:
            continue

        holidays = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Title')
            
            # Format date properly
            try:
                if 'T' in start:
                    date_obj = datetime.fromisoformat(start.replace('Z', '+00:00'))
                else:
                    date_obj = datetime.fromisoformat(start)
                formatted_date = date_obj.strftime("%B %d, %Y")
            except:
                formatted_date = start
            
            holidays.append({
                'title': summary,
                'date': formatted_date
            })
        
        if holidays:
            all_holidays[region] = holidays

    if not all_holidays:
        return {
            'status': 'success',
            'message': 'No upcoming holidays this month.',
            'data': {}
        }

    return {
        'status': 'success',
        'message': f'Found holidays in {len(all_holidays)} regions.',
        'data': all_holidays
    }

def list_holidays_next_month():
    """Display holidays for next month"""
    creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    
    calendars = get_all_holiday_calendars()
    if not calendars:
        return {
            'status': 'error',
            'message': 'No holiday calendars found. Make sure you are subscribed to them.',
            'data': None
        }

    now = datetime.now(pytz.UTC)
    # Get next month's start and end
    if now.month == 12:
        next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month_end = now.replace(year=now.year + 1, month=2, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month_start = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 11:
            next_month_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_end = now.replace(month=now.month + 2, day=1, hour=0, minute=0, second=0, microsecond=0)

    next_month_name = next_month_start.strftime("%B %Y")
    all_holidays = {}
    
    for region, cal_id in calendars.items():
        events_result = service.events().list(
            calendarId=cal_id,
            timeMin=next_month_start.isoformat(),
            timeMax=next_month_end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events:
            continue

        holidays = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No Title')
            
            # Format date properly
            try:
                if 'T' in start:
                    date_obj = datetime.fromisoformat(start.replace('Z', '+00:00'))
                else:
                    date_obj = datetime.fromisoformat(start)
                formatted_date = date_obj.strftime("%B %d, %Y")
            except:
                formatted_date = start
            
            holidays.append({
                'title': summary,
                'date': formatted_date
            })
        
        if holidays:
            all_holidays[region] = holidays

    if not all_holidays:
        return {
            'status': 'success',
            'message': f'No holidays in {next_month_name}.',
            'data': {}
        }

    return {
        'status': 'success',
        'message': f'Found holidays in {len(all_holidays)} regions for {next_month_name}.',
        'data': {'month': next_month_name, 'holidays': all_holidays}
    }
